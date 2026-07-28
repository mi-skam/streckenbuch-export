(() => {
  "use strict";

  const form = document.querySelector("#export-form");
  const fileInput = document.querySelector("#pdf-input");
  const dropZone = document.querySelector("#drop-zone");
  const dropTitle = document.querySelector("#drop-title");
  const fileMeta = document.querySelector("#file-meta");
  const exportButton = document.querySelector("#export-button");
  const statusPanel = document.querySelector("#status-panel");
  const statusTitle = document.querySelector("#status-title");
  const statusDetail = document.querySelector("#status-detail");
  const resultPanel = document.querySelector("#result-panel");
  const resultSummary = document.querySelector("#result-summary");
  const downloadList = document.querySelector("#download-list");
  const errorPanel = document.querySelector("#error-panel");
  const errorMessage = document.querySelector("#error-message");

  let selectedFile = null;
  let worker = null;
  let activeJob = null;
  let downloadUrls = [];

  const formatBytes = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    const units = ["KB", "MB", "GB"];
    let value = bytes / 1024;
    let unit = units[0];
    for (let index = 1; value >= 1024 && index < units.length; index += 1) {
      value /= 1024;
      unit = units[index];
    }
    return `${value.toLocaleString("de-DE", { maximumFractionDigits: 1 })} ${unit}`;
  };

  const isPdf = (file) =>
    file && (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"));

  const showError = (message) => {
    statusPanel.hidden = true;
    resultPanel.hidden = true;
    errorMessage.textContent = message;
    errorPanel.hidden = false;
  };

  const chooseFile = (file) => {
    if (!isPdf(file)) {
      selectedFile = null;
      dropZone.classList.remove("has-file");
      showError("Bitte wählen Sie eine PDF-Datei aus.");
      return;
    }

    selectedFile = file;
    errorPanel.hidden = true;
    resultPanel.hidden = true;
    dropZone.classList.add("has-file");
    dropTitle.textContent = file.name;
    fileMeta.textContent = `${formatBytes(file.size)} · PDF`;
    fileMeta.hidden = false;
  };

  const setBusy = (busy) => {
    exportButton.disabled = busy;
    fileInput.disabled = busy;
    form.querySelectorAll("input[type=radio], select").forEach((control) => {
      control.disabled = busy;
    });
    exportButton.querySelector("span").textContent = busy ? "Auswertung läuft …" : "Export starten";
  };

  const updateStatus = (title, detail) => {
    errorPanel.hidden = true;
    resultPanel.hidden = true;
    statusTitle.textContent = title;
    statusDetail.textContent = detail;
    statusPanel.hidden = false;
  };

  const clearDownloads = () => {
    downloadUrls.forEach((url) => URL.revokeObjectURL(url));
    downloadUrls = [];
    downloadList.replaceChildren();
  };

  const showResult = (summary, files) => {
    clearDownloads();
    statusPanel.hidden = true;
    errorPanel.hidden = true;
    resultSummary.textContent =
      `${summary.contacts.toLocaleString("de-DE")} eindeutige Fundstellen, ` +
      `${summary.duplicatesRemoved.toLocaleString("de-DE")} Dubletten entfernt, ` +
      `${summary.stations.toLocaleString("de-DE")} Betriebsstellen auf ` +
      `${summary.totalPages.toLocaleString("de-DE")} Seiten.`;

    files.forEach(({ name, type, buffer }) => {
      const url = URL.createObjectURL(new Blob([buffer], { type }));
      downloadUrls.push(url);
      const link = document.createElement("a");
      link.href = url;
      link.download = name;
      const label = document.createElement("span");
      label.textContent = name;
      const action = document.createElement("span");
      action.textContent = "Herunterladen ↓";
      link.append(label, action);
      downloadList.append(link);
    });

    resultPanel.hidden = false;
    resultPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  const ensureWorker = () => {
    if (worker) return worker;

    worker = new Worker("./export-worker.js?v=20260728.1");
    worker.addEventListener("message", ({ data }) => {
      if (!activeJob || data.jobId !== activeJob) return;

      if (data.type === "status") {
        updateStatus(data.title, data.detail);
        return;
      }

      setBusy(false);
      activeJob = null;
      if (data.type === "complete") {
        showResult(data.summary, data.files);
      } else if (data.type === "error") {
        showError(data.message || "Bei der Verarbeitung ist ein unbekannter Fehler aufgetreten.");
      }
    });

    worker.addEventListener("error", (event) => {
      if (!activeJob) return;
      setBusy(false);
      activeJob = null;
      showError(`Die Browser-Engine konnte nicht gestartet werden: ${event.message}`);
      worker.terminate();
      worker = null;
    });

    return worker;
  };

  fileInput.addEventListener("change", () => chooseFile(fileInput.files[0]));

  ["dragenter", "dragover"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      if (!fileInput.disabled) dropZone.classList.add("is-dragging");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.remove("is-dragging");
    });
  });

  dropZone.addEventListener("drop", (event) => {
    if (fileInput.disabled) return;
    chooseFile(event.dataTransfer.files[0]);
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!selectedFile) {
      showError("Bitte wählen Sie zuerst ein Streckenbuch-PDF aus.");
      return;
    }
    if (activeJob) return;

    clearDownloads();
    const data = new FormData(form);
    const jobId = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
    activeJob = jobId;
    setBusy(true);
    updateStatus(
      "Browser-Engine wird geladen …",
      "Beim ersten Start werden Python und die Export-Komponenten heruntergeladen."
    );

    try {
      const buffer = await selectedFile.arrayBuffer();
      ensureWorker().postMessage(
        {
          type: "export",
          jobId,
          fileName: selectedFile.name,
          format: data.get("format"),
          minConfidence: 0,
          buffer,
        },
        [buffer]
      );
    } catch (error) {
      activeJob = null;
      setBusy(false);
      showError(error instanceof Error ? error.message : String(error));
    }
  });

  window.addEventListener("beforeunload", clearDownloads);
})();
