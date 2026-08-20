using System.Diagnostics;
using System.Globalization;
using System.Text.Json;

namespace Whispers;

public sealed class MediaProcessor
{
    public static readonly HashSet<string> SupportedExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma",
        ".mp4", ".mkv", ".mov", ".avi", ".webm", ".mpeg", ".mpg", ".wmv", ".m4v"
    };

    private static readonly TimeSpan ChunkDuration = TimeSpan.FromMinutes(20);
    private const long ApiLimitBytes = 25L * 1024 * 1024;
    private readonly string _ffmpeg;
    private readonly string _ffprobe;

    public MediaProcessor(string? ffmpeg = null, string? ffprobe = null)
    {
        _ffmpeg = ffmpeg ?? ResolveTool("ffmpeg");
        _ffprobe = ffprobe ?? ResolveTool("ffprobe");
    }

    public static bool IsSupported(string path) =>
        File.Exists(path) && SupportedExtensions.Contains(Path.GetExtension(path));

    public async Task<MediaInfo> ProbeAsync(string inputPath, CancellationToken cancellationToken = default)
    {
        if (!IsSupported(inputPath))
            throw new InvalidDataException("Selecione um arquivo de áudio ou vídeo em um formato compatível.");

        var result = await RunAsync(_ffprobe,
            ["-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index:format=duration", "-of", "json", inputPath],
            cancellationToken);

        if (result.ExitCode != 0)
            throw new InvalidDataException("O arquivo não pôde ser lido ou está corrompido.");

        try
        {
            using var json = JsonDocument.Parse(result.StandardOutput);
            var root = json.RootElement;
            if (!root.TryGetProperty("streams", out var streams) || streams.GetArrayLength() == 0)
                throw new InvalidDataException("O arquivo selecionado não possui uma faixa de áudio.");

            if (!root.TryGetProperty("format", out var format) ||
                !format.TryGetProperty("duration", out var durationElement) ||
                !double.TryParse(durationElement.GetString(), NumberStyles.Float, CultureInfo.InvariantCulture, out var seconds) ||
                seconds <= 0)
                throw new InvalidDataException("Não foi possível determinar a duração do arquivo.");

            return new MediaInfo(TimeSpan.FromSeconds(seconds), new FileInfo(inputPath).Length);
        }
        catch (Exception ex) when (ex is JsonException or InvalidOperationException)
        {
            throw new InvalidDataException("O FFprobe retornou informações inválidas para este arquivo.", ex);
        }
    }

    public async Task<PreparedMedia> PrepareAsync(string inputPath, CancellationToken cancellationToken)
    {
        var temporaryDirectory = Path.Combine(Path.GetTempPath(), "Whispers", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temporaryDirectory);
        var outputPattern = Path.Combine(temporaryDirectory, "chunk-%04d.mp3");

        try
        {
            var result = await RunAsync(_ffmpeg,
                ["-y", "-v", "error", "-i", inputPath, "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
                 "-c:a", "libmp3lame", "-b:a", "64k", "-f", "segment", "-segment_time",
                 ((int)ChunkDuration.TotalSeconds).ToString(CultureInfo.InvariantCulture), "-reset_timestamps", "1", outputPattern],
                cancellationToken);

            if (result.ExitCode != 0)
                throw new InvalidDataException("Não foi possível extrair o áudio do arquivo selecionado.");

            var files = Directory.GetFiles(temporaryDirectory, "chunk-*.mp3").Order().ToArray();
            if (files.Length == 0)
                throw new InvalidDataException("Nenhum áudio utilizável foi encontrado.");
            if (files.Any(path => new FileInfo(path).Length >= ApiLimitBytes))
                throw new InvalidDataException("Uma parte do áudio excedeu o limite de 25 MB da API.");

            var chunks = files.Select((path, index) => new AudioChunk(path, ChunkDuration * index)).ToArray();
            return new PreparedMedia(temporaryDirectory, chunks);
        }
        catch
        {
            try { Directory.Delete(temporaryDirectory, true); } catch { }
            throw;
        }
    }

    private static string ResolveTool(string name)
    {
        var executable = OperatingSystem.IsWindows() ? name + ".exe" : name;
        var bundled = Path.Combine(AppContext.BaseDirectory, "tools", executable);
        return File.Exists(bundled) ? bundled : executable;
    }

    private static async Task<ProcessResult> RunAsync(
        string executable,
        IEnumerable<string> arguments,
        CancellationToken cancellationToken)
    {
        var startInfo = new ProcessStartInfo(executable)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        foreach (var argument in arguments)
            startInfo.ArgumentList.Add(argument);

        using var process = new Process { StartInfo = startInfo };
        try
        {
            if (!process.Start())
                throw new InvalidOperationException($"Não foi possível iniciar {executable}.");
        }
        catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or InvalidOperationException)
        {
            throw new InvalidOperationException("FFmpeg/FFprobe não foi encontrado na instalação.", ex);
        }

        var outputTask = process.StandardOutput.ReadToEndAsync(cancellationToken);
        var errorTask = process.StandardError.ReadToEndAsync(cancellationToken);
        try
        {
            await process.WaitForExitAsync(cancellationToken);
            return new ProcessResult(process.ExitCode, await outputTask, await errorTask);
        }
        catch (OperationCanceledException)
        {
            try
            {
                if (!process.HasExited)
                {
                    process.Kill(true);
                    await process.WaitForExitAsync();
                }
            }
            catch { }
            throw;
        }
    }

    private sealed record ProcessResult(int ExitCode, string StandardOutput, string StandardError);
}
