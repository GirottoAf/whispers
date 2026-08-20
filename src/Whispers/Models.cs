using System.Text.Json.Serialization;

namespace Whispers;

public sealed record HistoryEntry(
    Guid Id,
    string SourcePath,
    string OutputPath,
    DateTime CreatedAtUtc,
    bool HasTimestamps)
{
    [JsonIgnore] public string SourceName => Path.GetFileName(SourcePath);
    [JsonIgnore] public string OutputName => Path.GetFileName(OutputPath);
    [JsonIgnore] public string Mode => HasTimestamps ? "Com timestamps" : "Texto simples";
    [JsonIgnore] public string CreatedAt => CreatedAtUtc.ToLocalTime().ToString("dd/MM/yyyy HH:mm");
}

public sealed class AppState
{
    public string? ProtectedApiKey { get; set; }
    public List<HistoryEntry> History { get; set; } = [];
}

public sealed record MediaInfo(TimeSpan Duration, long Size);
public sealed record AudioChunk(string Path, TimeSpan Start);
public sealed record TranscriptSegment(double Start, double End, string Text);
public sealed record ChunkTranscript(string Text, IReadOnlyList<TranscriptSegment> Segments);
public sealed record WorkflowProgress(string Message, int Completed, int Total, bool IsIndeterminate = false);

public sealed class PreparedMedia(string temporaryDirectory, IReadOnlyList<AudioChunk> chunks) : IDisposable
{
    public IReadOnlyList<AudioChunk> Chunks { get; } = chunks;

    public void Dispose()
    {
        try
        {
            if (Directory.Exists(temporaryDirectory))
                Directory.Delete(temporaryDirectory, true);
        }
        catch (IOException)
        {
            // O sistema operacional também limpa a pasta temporária posteriormente.
        }
        catch (UnauthorizedAccessException)
        {
        }
    }
}

public sealed class TranscriptionException(string message, int? statusCode = null) : Exception(message)
{
    public int? StatusCode { get; } = statusCode;
}
