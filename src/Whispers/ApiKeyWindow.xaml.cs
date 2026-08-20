using System.Windows;

namespace Whispers;

public partial class ApiKeyWindow : Window
{
    public ApiKeyWindow(bool allowDelete)
    {
        InitializeComponent();
        DeleteButton.Visibility = allowDelete ? Visibility.Visible : Visibility.Collapsed;
        Loaded += (_, _) => ApiKeyBox.Focus();
    }

    public string? ApiKey { get; private set; }
    public bool DeleteRequested { get; private set; }

    private void Save_Click(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(ApiKeyBox.Password))
        {
            MessageBox.Show(this, "Cole uma chave da API antes de salvar.", "Chave necessária",
                MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        ApiKey = ApiKeyBox.Password.Trim();
        DialogResult = true;
    }

    private void Delete_Click(object sender, RoutedEventArgs e)
    {
        if (MessageBox.Show(this, "Remover a chave salva neste computador?", "Remover chave",
                MessageBoxButton.YesNo, MessageBoxImage.Question) != MessageBoxResult.Yes)
            return;

        DeleteRequested = true;
        DialogResult = true;
    }
}
