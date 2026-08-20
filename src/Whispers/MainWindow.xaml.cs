using Microsoft.Win32;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Windows;

namespace Whispers;

public partial class MainWindow : Window
{
    private readonly AppStateStore _store = new();
    private readonly MediaProcessor _mediaProcessor = new();
    private readonly ObservableCollection<HistoryEntry> _history;
    private string? _selectedFile;
    private CancellationTokenSource? _workCancellation;
    private bool _busy;

    public MainWindow()
    {
        InitializeComponent();
        _history = new ObservableCollection<HistoryEntry>(_store.State.History);
        HistoryList.ItemsSource = _history;
        Loaded += MainWindow_Loaded;
        Closing += (_, _) => _workCancellation?.Cancel();
    }

    private void MainWindow_Loaded(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(_store.State.ProtectedApiKey))
            PromptForKey(false);
    }

    private void ConfigureKey_Click(object sender, RoutedEventArgs e) =>
        PromptForKey(!string.IsNullOrWhiteSpace(_store.State.ProtectedApiKey));

    private bool PromptForKey(bool allowDelete)
    {
        var dialog = new ApiKeyWindow(allowDelete) { Owner = this };
        if (dialog.ShowDialog() != true)
            return false;

        if (dialog.DeleteRequested)
        {
            _store.ClearApiKey();
            StatusText.Text = "Chave removida deste computador.";
            return false;
        }

        _store.SetApiKey(dialog.ApiKey!);
        StatusText.Text = "Chave salva com proteção do Windows.";
        return true;
    }

    private async void SelectFile_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Selecione um áudio ou vídeo",
            CheckFileExists = true,
            Multiselect = false,
            Filter = "Áudio e vídeo|*.mp3;*.wav;*.m4a;*.aac;*.flac;*.ogg;*.opus;*.wma;*.mp4;*.mkv;*.mov;*.avi;*.webm;*.mpeg;*.mpg;*.wmv;*.m4v|Todos os arquivos|*.*"
        };
        if (dialog.ShowDialog(this) == true)
            await SelectFileAsync(dialog.FileName);
    }

    private async Task SelectFileAsync(string path)
    {
        if (_busy)
            return;

        try
        {
            SelectButton.IsEnabled = false;
            TranscribeButton.IsEnabled = false;
            StatusText.Text = "Analisando o arquivo…";
            var media = await _mediaProcessor.ProbeAsync(path);
            _selectedFile = path;
            SelectedFileText.Text = Path.GetFileName(path);
            FileDetailsText.Text = $"{media.Size / 1024d / 1024d:N1} MB • {FormatDuration(media.Duration)}";
            StatusText.Text = "Arquivo pronto para transcrição.";
            TranscribeButton.IsEnabled = true;
        }
        catch (Exception ex) when (ex is InvalidDataException or InvalidOperationException)
        {
            _selectedFile = null;
            SelectedFileText.Text = "Nenhum arquivo selecionado";
            FileDetailsText.Text = "";
            StatusText.Text = ex.Message;
            MessageBox.Show(this, ex.Message, "Arquivo não aceito", MessageBoxButton.OK, MessageBoxImage.Warning);
        }
        finally
        {
            SelectButton.IsEnabled = true;
        }
    }

    private async void Transcribe_Click(object sender, RoutedEventArgs e)
    {
        if (_selectedFile is null)
            return;

        string? apiKey;
        try
        {
            apiKey = _store.GetApiKey();
        }
        catch (InvalidOperationException ex)
        {
            MessageBox.Show(this, ex.Message, "Chave indisponível", MessageBoxButton.OK, MessageBoxImage.Warning);
            PromptForKey(true);
            return;
        }

        if (apiKey is null && (!PromptForKey(false) || (apiKey = _store.GetApiKey()) is null))
            return;

        _workCancellation = new CancellationTokenSource();
        SetBusy(true);
        var timestamps = TimestampCheck.IsChecked == true;
        var progress = new Progress<WorkflowProgress>(UpdateProgress);

        try
        {
            var workflow = new TranscriptionWorkflow(_mediaProcessor);
            var outputPath = await workflow.RunAsync(
                _selectedFile, apiKey, timestamps, progress, _workCancellation.Token);
            var entry = new HistoryEntry(Guid.NewGuid(), _selectedFile, outputPath, DateTime.UtcNow, timestamps);
            _store.AddHistory(entry);
            _history.Insert(0, entry);
            StatusText.Text = $"Concluído: {Path.GetFileName(outputPath)}";
            Progress.IsIndeterminate = false;
            Progress.Maximum = 1;
            Progress.Value = 1;
        }
        catch (OperationCanceledException)
        {
            StatusText.Text = "Transcrição cancelada. Nenhum TXT parcial foi salvo.";
        }
        catch (Exception ex) when (ex is TranscriptionException or InvalidDataException or IOException or UnauthorizedAccessException)
        {
            StatusText.Text = ex.Message;
            MessageBox.Show(this, ex.Message, "Não foi possível transcrever", MessageBoxButton.OK, MessageBoxImage.Error);
        }
        catch (Exception ex)
        {
            StatusText.Text = "Ocorreu um erro inesperado.";
            MessageBox.Show(this, $"Ocorreu um erro inesperado: {ex.Message}", "Erro",
                MessageBoxButton.OK, MessageBoxImage.Error);
        }
        finally
        {
            _workCancellation.Dispose();
            _workCancellation = null;
            SetBusy(false);
        }
    }

    private void UpdateProgress(WorkflowProgress progress)
    {
        StatusText.Text = progress.Message;
        Progress.IsIndeterminate = progress.IsIndeterminate;
        if (!progress.IsIndeterminate)
        {
            Progress.Maximum = Math.Max(1, progress.Total);
            Progress.Value = progress.Completed;
        }
    }

    private void SetBusy(bool busy)
    {
        _busy = busy;
        SelectButton.IsEnabled = !busy;
        TimestampCheck.IsEnabled = !busy;
        TranscribeButton.IsEnabled = !busy && _selectedFile is not null;
        CancelButton.IsEnabled = busy;
    }

    private void Cancel_Click(object sender, RoutedEventArgs e)
    {
        CancelButton.IsEnabled = false;
        StatusText.Text = "Cancelando…";
        _workCancellation?.Cancel();
    }

    private void Window_PreviewDragOver(object sender, DragEventArgs e)
    {
        e.Effects = !_busy && GetSingleDroppedFile(e.Data) is { } path && MediaProcessor.IsSupported(path)
            ? DragDropEffects.Copy
            : DragDropEffects.None;
        e.Handled = true;
    }

    private async void Window_Drop(object sender, DragEventArgs e)
    {
        var path = GetSingleDroppedFile(e.Data);
        if (path is null)
        {
            MessageBox.Show(this, "Arraste apenas um arquivo por vez.", "Arquivo não aceito",
                MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }
        await SelectFileAsync(path);
    }

    private static string? GetSingleDroppedFile(IDataObject data)
    {
        if (!data.GetDataPresent(DataFormats.FileDrop) || data.GetData(DataFormats.FileDrop) is not string[] { Length: 1 } files)
            return null;
        return files[0];
    }

    private void OpenOutput_Click(object sender, RoutedEventArgs e)
    {
        if (HistoryList.SelectedItem is HistoryEntry entry)
            OpenPath(entry.OutputPath, false);
    }

    private void OpenFolder_Click(object sender, RoutedEventArgs e)
    {
        if (HistoryList.SelectedItem is HistoryEntry entry && Path.GetDirectoryName(entry.OutputPath) is { } directory)
            OpenPath(directory, true);
    }

    private void OpenPath(string path, bool directory)
    {
        if (!(directory ? Directory.Exists(path) : File.Exists(path)))
        {
            MessageBox.Show(this, "O arquivo ou pasta não existe mais.", "Item indisponível",
                MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }
        try
        {
            Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
        }
        catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or InvalidOperationException)
        {
            MessageBox.Show(this, "O Windows não conseguiu abrir este item.", "Não foi possível abrir",
                MessageBoxButton.OK, MessageBoxImage.Warning);
        }
    }

    private void RemoveHistory_Click(object sender, RoutedEventArgs e)
    {
        if (HistoryList.SelectedItem is not HistoryEntry entry)
            return;
        _store.RemoveHistory(entry.Id);
        _history.Remove(entry);
    }

    private void ClearHistory_Click(object sender, RoutedEventArgs e)
    {
        if (_history.Count == 0 || MessageBox.Show(this, "Limpar todo o histórico? Os arquivos TXT não serão apagados.",
                "Limpar histórico", MessageBoxButton.YesNo, MessageBoxImage.Question) != MessageBoxResult.Yes)
            return;
        _store.ClearHistory();
        _history.Clear();
    }

    private static string FormatDuration(TimeSpan duration) => duration.TotalHours >= 1
        ? $"{(long)duration.TotalHours:00}:{duration.Minutes:00}:{duration.Seconds:00}"
        : $"{duration.Minutes:00}:{duration.Seconds:00}";
}
