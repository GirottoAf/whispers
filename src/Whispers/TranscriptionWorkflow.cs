using System.Text;

namespace Whispers;

public sealed class TranscriptionWorkflow(MediaProcessor mediaProcessor)
{
    public async Task<string> RunAsync(
        string sourcePath,
        string apiKey,
        bool timestamps,
        string outputDirectory,
        IProgress<WorkflowProgress>? progress,
        CancellationToken cancellationToken)
    {
        progress?.Report(new WorkflowProgress("Extraindo e preparando o áudio…", 0, 1, true));
        using var prepared = await mediaProcessor.PrepareAsync(sourcePath, cancellationToken);
        using var client = new OpenAiTranscriptionClient(apiKey);
        var text = new StringBuilder();

        for (var index = 0; index < prepared.Chunks.Count; index++)
        {
            var chunk = prepared.Chunks[index];
            progress?.Report(new WorkflowProgress(
                $"Transcrevendo parte {index + 1} de {prepared.Chunks.Count}…", index, prepared.Chunks.Count));
            var result = await client.TranscribeAsync(chunk.Path, timestamps, cancellationToken);

            if (timestamps)
            {
                foreach (var segment in result.Segments)
                {
                    var globalStart = chunk.Start.TotalSeconds + segment.Start;
                    text.Append('[').Append(OutputFile.FormatTimestamp(globalStart)).Append("] ")
                        .AppendLine(segment.Text.Trim());
                }
            }
            else
            {
                if (text.Length > 0)
                    text.AppendLine().AppendLine();
                text.Append(result.Text.Trim());
            }
        }

        progress?.Report(new WorkflowProgress("Salvando o arquivo…", prepared.Chunks.Count, prepared.Chunks.Count));
        var outputPath = OutputFile.CreateUniquePath(sourcePath, timestamps, outputDirectory);
        await OutputFile.WriteAsync(outputPath, text.ToString(), cancellationToken);
        return outputPath;
    }
}
