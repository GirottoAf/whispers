using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Whispers;

public sealed class AppStateStore
{
    private static readonly byte[] Entropy = Encoding.UTF8.GetBytes("Whispers/v1");
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };
    private readonly string _directory;
    private readonly string _path;

    public AppStateStore(string? directory = null)
    {
        _directory = directory ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Whispers");
        _path = Path.Combine(_directory, "app-state.json");
        State = Load();
    }

    public AppState State { get; private set; }

    public string? GetApiKey()
    {
        if (string.IsNullOrWhiteSpace(State.ProtectedApiKey))
            return null;

        try
        {
            var encrypted = Convert.FromBase64String(State.ProtectedApiKey);
            return Encoding.UTF8.GetString(ProtectedData.Unprotect(encrypted, Entropy, DataProtectionScope.CurrentUser));
        }
        catch (Exception ex) when (ex is CryptographicException or FormatException)
        {
            throw new InvalidOperationException("Não foi possível ler a chave salva. Substitua-a nas configurações.", ex);
        }
    }

    public void SetApiKey(string apiKey)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(apiKey);
        var encrypted = ProtectedData.Protect(
            Encoding.UTF8.GetBytes(apiKey.Trim()), Entropy, DataProtectionScope.CurrentUser);
        State.ProtectedApiKey = Convert.ToBase64String(encrypted);
        Save();
    }

    public void ClearApiKey()
    {
        State.ProtectedApiKey = null;
        Save();
    }

    public void AddHistory(HistoryEntry entry)
    {
        State.History.Insert(0, entry);
        Save();
    }

    public void RemoveHistory(Guid id)
    {
        State.History.RemoveAll(item => item.Id == id);
        Save();
    }

    public void ClearHistory()
    {
        State.History.Clear();
        Save();
    }

    private AppState Load()
    {
        if (!File.Exists(_path))
            return new AppState();

        try
        {
            return JsonSerializer.Deserialize<AppState>(File.ReadAllText(_path), JsonOptions) ?? new AppState();
        }
        catch (JsonException)
        {
            Directory.CreateDirectory(_directory);
            File.Move(_path, $"{_path}.corrupt-{DateTime.UtcNow:yyyyMMddHHmmss}", true);
            return new AppState();
        }
    }

    private void Save()
    {
        Directory.CreateDirectory(_directory);
        var temporaryPath = _path + ".tmp";
        File.WriteAllText(temporaryPath, JsonSerializer.Serialize(State, JsonOptions), new UTF8Encoding(false));
        File.Move(temporaryPath, _path, true);
    }
}
