using System.Text;

namespace Whispers;

public static class OutputFile
{
    public static string CreateUniquePath(string sourcePath, bool timestamps, string outputDirectory)
    {
        var baseName = Path.GetFileNameWithoutExtension(sourcePath) + (timestamps ? "_timestamps" : "");
        var candidate = Path.Combine(outputDirectory, baseName + ".txt");
        for (var number = 2; File.Exists(candidate); number++)
            candidate = Path.Combine(outputDirectory, $"{baseName} ({number}).txt");
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
