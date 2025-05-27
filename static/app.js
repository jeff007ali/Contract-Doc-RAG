let pdfDoc = null;
let pageNum = 1;
let canvas = document.getElementById('pdf-canvas');
let ctx = canvas.getContext('2d');
let currentFile = null;
let contractId = null;

document.getElementById('upload-btn').addEventListener('click', () => {
  const fileInput = document.getElementById('pdf-upload');
  const file = fileInput.files[0];
  if (!file) return alert("Please select a PDF first.");

  currentFile = file;

  const formData = new FormData();
  formData.append("file", file);

  fetch('/upload', {
    method: 'POST',
    body: formData
  })
  .then(res => res.json())
  .then(data => {
    contractId = data.contract_id;
    const fileURL = URL.createObjectURL(file);
    loadPDF(fileURL);
  })
  .catch(err => console.error("Upload failed:", err));
});

function loadPDF(url) {
  pdfjsLib.getDocument(url).promise.then(pdf => {
    pdfDoc = pdf;
    pageNum = 1;
    document.getElementById('page-count').textContent = pdf.numPages;
    renderPage(pageNum);
  });
}

function renderPage(num) {
  pdfDoc.getPage(num).then(page => {
    const viewport = page.getViewport({ scale: 1.5 });
    canvas.height = viewport.height;
    canvas.width = viewport.width;

    page.render({
      canvasContext: ctx,
      viewport: viewport
    });

    document.getElementById('page-num').textContent = num;
  });
}

document.getElementById('prev-page').addEventListener('click', () => {
  if (pageNum <= 1) return;
  pageNum--;
  renderPage(pageNum);
});

document.getElementById('next-page').addEventListener('click', () => {
  if (pageNum >= pdfDoc.numPages) return;
  pageNum++;
  renderPage(pageNum);
});

document.getElementById('ask-button').addEventListener('click', () => {
  const question = document.getElementById('question-input').value.trim();
  if (!question || !currentFile) return alert("Upload a PDF and enter a question.");

  fetch('/ask', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ question: question, contract_id: contractId })
  })
  .then(res => res.json())
  .then(data => {
    document.getElementById('answer-container').innerText = data.answer || "No answer found.";
  })
  .catch(err => {
    console.error("Error asking question:", err);
  });
});

function highlightText(text) {
    // Stub: highlight logic using PDF.js textLayer
    console.log("Highlight text:", text);
}
