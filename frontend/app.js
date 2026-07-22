// Simple vanilla JS client for the TMO-AI chat backend.
// No build step required: open index.html directly or serve via any static server.

const els = {
  apiBase: document.getElementById("apiBase"),
  messages: document.getElementById("messages"),
  chatForm: document.getElementById("chatForm"),
  messageInput: document.getElementById("messageInput"),
  sendBtn: document.getElementById("sendBtn"),
  chatHistoryList: document.getElementById("chatHistoryList"),
  memoriesList: document.getElementById("memoriesList"),
  memoryForm: document.getElementById("memoryForm"),
  memoryKey: document.getElementById("memoryKey"),
  memoryValue: document.getElementById("memoryValue"),
  refreshChats: document.getElementById("refreshChats"),
  refreshMemories: document.getElementById("refreshMemories"),
  documentsList: document.getElementById("documentsList"),
  refreshDocuments: document.getElementById("refreshDocuments"),
  uploadForm: document.getElementById("uploadForm"),
  uploadFile: document.getElementById("uploadFile"),
  uploadBtn: document.getElementById("uploadBtn"),
  uploadStatus: document.getElementById("uploadStatus"),
  documentSelect: document.getElementById("documentSelect"),
  modelSelect: document.getElementById("modelSelect"),
  modelCustom: document.getElementById("modelCustom"),
};

function getApiBase() {
  // Default to the proxied `/api` path so the frontend uses the same origin
  // and avoids browser private network / CORS issues when served from HTTPS.
  return (els.apiBase.value || "/api").replace(/\/+$/, "");
}

function addMessage(role, text, docId) {
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.textContent = text;
  if (docId) {
    const tag = document.createElement("span");
    tag.className = "doc-tag";
    tag.textContent = `document_id: ${docId}`;
    div.appendChild(tag);
  }
  els.messages.appendChild(div);
  els.messages.scrollTop = els.messages.scrollHeight;
  return div;
}

function formatDate(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch (e) {
    return iso || "";
  }
}

async function sendMessage(message, documentId) {
  const res = await fetch(`${getApiBase()}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, document_id: documentId || null, model: getSelectedModel() }),
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => res.statusText);
    throw new Error(`HTTP ${res.status}: ${errText}`);
  }

  return res.json();
}

async function loadChats() {
  els.chatHistoryList.innerHTML = `<li class="empty">Memuat...</li>`;
  try {
    const res = await fetch(`${getApiBase()}/chats?page=1&page_size=20`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    els.chatHistoryList.innerHTML = "";
    if (!data.items || data.items.length === 0) {
      els.chatHistoryList.innerHTML = `<li class="empty">Belum ada chat</li>`;
      return;
    }

    for (const item of data.items) {
      const li = document.createElement("li");
      const title = document.createElement("span");
      title.className = "item-title";
      title.textContent = item.message;
      const sub = document.createElement("span");
      sub.className = "item-sub";
      sub.textContent = formatDate(item.created_at);
      li.appendChild(title);
      li.appendChild(sub);
      els.chatHistoryList.appendChild(li);
    }
  } catch (e) {
    els.chatHistoryList.innerHTML = `<li class="empty">Gagal memuat: ${e.message}</li>`;
  }
}

async function loadMemories() {
  els.memoriesList.innerHTML = `<li class="empty">Memuat...</li>`;
  try {
    const res = await fetch(`${getApiBase()}/memories?limit=50`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    els.memoriesList.innerHTML = "";
    if (!data.items || data.items.length === 0) {
      els.memoriesList.innerHTML = `<li class="empty">Belum ada memory</li>`;
      return;
    }

    for (const item of data.items) {
      const li = document.createElement("li");
      const title = document.createElement("span");
      title.className = "item-title";
      title.textContent = item.key ? `${item.key}` : "(tanpa key)";
      const sub = document.createElement("span");
      sub.className = "item-sub";
      sub.textContent = item.value;
      li.appendChild(title);
      li.appendChild(sub);
      els.memoriesList.appendChild(li);
    }
  } catch (e) {
    els.memoriesList.innerHTML = `<li class="empty">Gagal memuat: ${e.message}</li>`;
  }
}

els.chatForm.addEventListener("submit", async (evt) => {
  evt.preventDefault();
  const message = els.messageInput.value.trim();
  if (!message) return;

  const documentId = els.documentSelect.value || null;
  const model = getSelectedModel();

  addMessage("user", message, documentId);
  els.messageInput.value = "";
  els.sendBtn.disabled = true;

  const thinkingEl = addMessage("system", "Mengetik...");

  try {
    const data = await sendMessage(message, documentId);
    thinkingEl.remove();
    addMessage("ai", data.response, data.document_id);
  } catch (e) {
    thinkingEl.remove();
    addMessage("system", `Error: ${e.message}`);
  } finally {
    els.sendBtn.disabled = false;
    els.messageInput.focus();
    loadChats();
    loadMemories();
  }
});

function getSelectedModel() {
  const sel = els.modelSelect.value || "";
  if (sel === "custom") {
    return els.modelCustom.value.trim() || null;
  }
  return sel || null;
}

els.modelSelect.addEventListener("change", (e) => {
  if (els.modelSelect.value === "custom") {
    els.modelCustom.style.display = "inline-block";
    els.modelCustom.focus();
  } else {
    els.modelCustom.style.display = "none";
  }
});

els.memoryForm.addEventListener("submit", async (evt) => {
  evt.preventDefault();
  const key = els.memoryKey.value.trim() || null;
  const value = els.memoryValue.value.trim();
  if (!value) return;

  try {
    const res = await fetch(`${getApiBase()}/memories`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    els.memoryKey.value = "";
    els.memoryValue.value = "";
    loadMemories();
  } catch (e) {
    alert(`Gagal menyimpan memory: ${e.message}`);
  }
});

async function loadDocuments() {
  els.documentsList.innerHTML = `<li class="empty">Memuat...</li>`;
  try {
    const res = await fetch(`${getApiBase()}/documents`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const docs = await res.json();

    els.documentsList.innerHTML = "";
    const selectedValue = els.documentSelect.value;
    els.documentSelect.innerHTML = `<option value="">(otomatis / tanpa dokumen)</option>`;

    if (!docs || docs.length === 0) {
      els.documentsList.innerHTML = `<li class="empty">Belum ada dokumen</li>`;
      return;
    }

    for (const doc of docs) {
      const li = document.createElement("li");
      const title = document.createElement("span");
      title.className = "item-title";
      title.textContent = doc.filename || doc.document_id;
      const sub = document.createElement("span");
      sub.className = "item-sub";
      sub.textContent = `${doc.document_id}${doc.pages ? ` \u00b7 ${doc.pages} hlm` : ""}`;
      li.appendChild(title);
      li.appendChild(sub);
      els.documentsList.appendChild(li);

      const opt = document.createElement("option");
      opt.value = doc.document_id;
      opt.textContent = doc.filename || doc.document_id;
      els.documentSelect.appendChild(opt);
    }

    // restore previous selection if it still exists
    if (selectedValue) {
      els.documentSelect.value = selectedValue;
    }
  } catch (e) {
    els.documentsList.innerHTML = `<li class="empty">Gagal memuat: ${e.message}</li>`;
  }
}

els.uploadForm.addEventListener("submit", async (evt) => {
  evt.preventDefault();
  const file = els.uploadFile.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  els.uploadBtn.disabled = true;
  els.uploadStatus.textContent = "Mengunggah...";

  try {
    const res = await fetch(`${getApiBase()}/upload`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const errText = await res.text().catch(() => res.statusText);
      throw new Error(`HTTP ${res.status}: ${errText}`);
    }
    const data = await res.json();
    els.uploadStatus.textContent = `Berhasil: ${data.filename}`;
    els.uploadFile.value = "";
    await loadDocuments();
    // auto-select the newly uploaded document
    els.documentSelect.value = data.document_id;
  } catch (e) {
    els.uploadStatus.textContent = `Gagal: ${e.message}`;
  } finally {
    els.uploadBtn.disabled = false;
  }
});

els.refreshDocuments.addEventListener("click", loadDocuments);
els.refreshChats.addEventListener("click", loadChats);
els.refreshMemories.addEventListener("click", loadMemories);

// initial load
addMessage("system", "Selamat datang! Ketik pesan untuk mulai chat dengan TMO-AI.");
loadDocuments();
loadChats();
loadMemories();
