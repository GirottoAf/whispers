using System.Text;

namespace Whispers;

public static class OutputFile
{
    public static string EnsureOutputDirectory(string? preferredDirectory = null, string? fallbackDirectory = null)
    {
        preferredDirectory ??= Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "Whispers");
        fallbackDirectory ??= Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Documents", "Whispers");

        try
        {
            Directory.CreateDirectory(preferredDirectory);
            return preferredDirectory;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or NotSupportedException)
        {
            Directory.CreateDirectory(fallbackDirectory);
            return fallbackDirectory;
        }
    }

    public static string CreateUniquePath(string sourcePath, bool timestamps, string? outputDirectory = null)
    {
        var directory = outputDirectory ?? EnsureOutputDirectory();
        if (outputDirectory is not null)
            Directory.CreateDirectory(directory);
        var baseName = Path.GetFileNameWithoutExtension(sourcePath) + (timestamps ? "_timestamps" : "");
        var candidate = Path.Combine(directory, baseName + ".txt");
        for (var number = 2; File.Exists(candidate); number++)
            candidate = Path.Combine(directory, $"{baseName} ({number}).txt");
        return candidate;
    }

    public static string FormatTimestamp(double seconds)
    {
        var total = Math.Max(0, (long)Math.Floor(seconds));
        return $"{total / 3600:00}:{total / 60 % 60:00}:{total % 60:00}";
    }

    public static async Task WriteAsync(string path, string content, CancellationToken cancellationToken)
    {
        var temporaryPath = path + ".tmp";
        try
        {
            await File.WriteAllTextAsync(temporaryPath, content.Trim() + Environment.NewLine,
                new UTF8Encoding(false), cancellationToken);
            File.Move(temporaryPath, path);
        }
        catch
        {
            try { File.Delete(temporaryPath); } catch { }
            throw;
        }
    }
}
