function makeScenarioDownloadName(name: string) {
  const base = name.trim() || "untitled-scenario";
  return `${base}.scenario.json`;
}

export function downloadScenarioFile(name: string, scenario: unknown) {
  const blob = new Blob([JSON.stringify(scenario, null, 2)], {
    type: "application/json",
  });

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = makeScenarioDownloadName(name);
  anchor.click();
  URL.revokeObjectURL(url);
}

export async function readScenarioFile(file: File): Promise<unknown> {
  const text = await file.text();
  return JSON.parse(text);
}
