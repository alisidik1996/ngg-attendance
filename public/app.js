const API_BASE_URL = "";
let activeOrderNumber = "";
let currentUser = null;

function setButtonLoading(btn, loading, originalText) {
    if (!btn) return;
    if (loading) {
        btn.disabled = true;
        btn.classList.add("btn-loading");
        btn.dataset.originalText = btn.innerText;
        btn.innerText = originalText || "Memproses...";
    } else {
        btn.disabled = false;
        btn.classList.remove("btn-loading");
        btn.innerText = btn.dataset.originalText || originalText;
    }
}

document.getElementById("search_keyword").addEventListener("keypress", function (e) {
    if (e.key === "Enter") searchParticipant();
});

window.addEventListener("load", () => {
    updateListSortIndicators();
    bootApp();
});

function showToast(message) {
    const toastEl = document.getElementById('liveToast');
    const bodyEl = document.getElementById('toast-body');
    if (!toastEl || !bodyEl) {
        alert(message);
        return;
    }
    bodyEl.innerText = String(message);
    new bootstrap.Toast(toastEl).show();
}

function getErrorMessage(detail) {
    if (!detail) return "";
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map(d => d.msg || JSON.stringify(d)).join(", ");
    if (typeof detail === "object") return detail.msg || detail.detail || JSON.stringify(detail);
    return String(detail);
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

async function fetchJson(url, options) {
    const response = await fetch(url, options);
    let data = null;
    try {
        data = await response.json();
    } catch (e) {
        data = null;
    }
    if (!response.ok) {
        const err = new Error(
            (data && getErrorMessage(data.detail)) || `HTTP ${response.status}`
        );
        err.status = response.status;
        err.data = data;
        if (response.status === 401 && !String(url).includes("/api/auth/")) {
            showLogin("Sesi berakhir. Silakan login kembali.");
        } else if (response.status === 403) {
            showToast(err.message || "Akses ditolak");
        }
        throw err;
    }
    return data;
}

async function fetchStats() {
    try {
        const res = await fetchJson(`${API_BASE_URL}/api/registration/stats`);
        if (res.status === "success") {
            const s = res.statistics;
            document.getElementById("live-stats").textContent = `Total: ${s.total_peserta} | Race Pack: ${s.race_pack_diambil}/${s.total_peserta} | Hadir: ${s.hadir_hari_h}`;
        }
    } catch (error) {
        console.error("Gagal load statistik", error);
    }
}

async function searchParticipant() {
    const keyword = document.getElementById("search_keyword").value.trim();
    if (!keyword) { alert("Masukkan keyword pencarian!"); return; }

    const btn = document.getElementById("btn-search");
    setButtonLoading(btn, true, "Mencari...");

    try {
        const res = await fetchJson(`${API_BASE_URL}/api/registration/search?keyword=${encodeURIComponent(keyword)}`);

        if (res.data && res.data.length > 0) {
            if (res.data.length === 1) {
                showParticipantDetail(res.data[0]);
            } else {
                showSearchResults(res.data);
            }
        } else {
            alert("Peserta tidak ditemukan.");
            resetView();
        }
    } catch (error) {
        console.error("Gagal mencari peserta", error);
        alert(error.message || "Koneksi ke backend gagal!");
    } finally {
        setButtonLoading(btn, false, "Cari");
    }
}

function showSearchResults(data) {
    document.getElementById("placeholder-box").classList.add("d-none");
    document.getElementById("result-container").classList.add("d-none");

    const container = document.getElementById("search-results-container");
    const tbody = document.getElementById("search-results-body");
    container.classList.remove("d-none");

    tbody.innerHTML = "";
    data.forEach(row => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td style="font-weight:600;">${escapeHtml(row.order_number || "-")}</td>
            <td class="text-break-safe" style="min-width: 130px;">${escapeHtml(row.nama_lengkap_ibu || "-")}</td>
            <td class="text-nowrap">${escapeHtml(row.nomor_wa || "-")}</td>
            <td class="text-break-safe" style="min-width: 100px;">${escapeHtml(row.item_name || "-")}</td>
            <td class="text-center">
                <button class="btn btn-sm btn-black text-nowrap">Pilih</button>
            </td>`;
        const pickBtn = tr.querySelector("button");
        pickBtn.addEventListener("click", () => selectParticipant(row.order_number, pickBtn));
        tbody.appendChild(tr);
    });
}

async function selectParticipant(orderNo, btn) {
    setButtonLoading(btn, true, "Memuat...");

    try {
        const result = await fetchJson(`${API_BASE_URL}/api/registration/participant/${encodeURIComponent(orderNo)}`);
        showParticipantDetail(result.data);
    } catch (error) {
        console.error("Gagal memuat peserta", error);
        alert(error.message || "Peserta tidak ditemukan.");
    } finally {
        setButtonLoading(btn, false, "Pilih");
    }
}

function showParticipantDetail(data) {
    document.getElementById("placeholder-box").classList.add("d-none");
    document.getElementById("search-results-container").classList.add("d-none");
    document.getElementById("result-container").classList.remove("d-none");

    activeOrderNumber = data.order_number || "";

    document.getElementById("badge-order").textContent = `No: ${data.order_number || "-"}`;
    document.getElementById("res-nama").textContent = data.nama_lengkap_ibu || "-";
    document.getElementById("res-nama-ayah").textContent = data.nama_lengkap_ayah || "-";
    document.getElementById("res-anak").textContent = data.nama_anak || "-";
    document.getElementById("res-usia").textContent = data.usia_bayi || "-";
    document.getElementById("res-item").textContent = data.item_name || data.paket || "-";
    document.getElementById("res-kaos-ibu").textContent = data.uk_kaos_ibu || "-";
    document.getElementById("res-kaos-ayah").textContent = data.uk_kaos_ayah || "-";
    document.getElementById("res-order-status").textContent = data.order_status || "-";

    const statusRp = String(data.status_diambil || "").trim().toLowerCase();
    const badgeRp = document.getElementById("res-status-rp");
    const btnRp = document.getElementById("btn-racepack");

    if (statusRp === "sudah") {
        badgeRp.className = "badge bg-ngg-black fs-6 text-break-safe mt-1";
        badgeRp.textContent = "SUDAH (" + (data.waktu_diambil || "") + ")";
        btnRp.disabled = false;
        btnRp.className = "btn btn-undo flex-grow-1";
        btnRp.textContent = "Batalkan Ambil Race Pack";
        btnRp.onclick = doUndoCheckIn;
    } else {
        badgeRp.className = "badge bg-ngg-white text-ngg-black fs-6 text-break-safe mt-1";
        badgeRp.style.border = "1px solid rgba(0,0,0,0.1)";
        badgeRp.textContent = "BELUM";
        btnRp.disabled = false;
        btnRp.className = "btn btn-black flex-grow-1";
        btnRp.textContent = "Ambil Race Pack";
        btnRp.onclick = doCheckIn;
    }

    const statusHadir = String(data.status_hadir || "").trim().toLowerCase();
    const badgeHadir = document.getElementById("res-status-hadir");
    const btnHadir = document.getElementById("btn-attendance");

    if (statusHadir === "hadir") {
        badgeHadir.className = "badge bg-ngg-black fs-6 text-break-safe mt-1";
        badgeHadir.textContent = "SUDAH (" + (data.waktu_hadir || "") + ")";
        btnHadir.disabled = false;
        btnHadir.className = "btn btn-undo flex-grow-1";
        btnHadir.textContent = "Batalkan Status Hadir";
        btnHadir.onclick = doUndoAttendance;
    } else {
        badgeHadir.className = "badge bg-ngg-white text-ngg-black fs-6 text-break-safe mt-1";
        badgeHadir.style.border = "1px solid rgba(0,0,0,0.1)";
        badgeHadir.textContent = "BELUM";
        btnHadir.disabled = false;
        btnHadir.className = "btn btn-blue flex-grow-1";
        btnHadir.textContent = "Absen Hadir";
        btnHadir.onclick = doAttendance;
    }
}

async function doCheckIn() {
    if (!activeOrderNumber) return;
    const btn = document.getElementById("btn-racepack");
    setButtonLoading(btn, true, "Memproses...");

    try {
        await fetchJson(`${API_BASE_URL}/api/registration/check-in`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ no_order: activeOrderNumber })
        });
        showToast("Race pack berhasil dicatat!");
        void refreshCurrentView();
        void fetchStats();
    } catch (e) {
        console.error("Gagal check-in", e);
        showToast(e.message || "Gagal koneksi server");
    } finally {
        setButtonLoading(btn, false, "Ambil Race Pack");
    }
}

async function doUndoCheckIn() {
    if (!activeOrderNumber) return;
    if (!confirm("Batalkan ambil race pack untuk peserta ini?")) return;

    const btn = document.getElementById("btn-racepack");
    setButtonLoading(btn, true, "Memproses...");

    try {
        await fetchJson(`${API_BASE_URL}/api/registration/check-in/undo`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ no_order: activeOrderNumber })
        });
        showToast("Ambil race pack dibatalkan!");
        void refreshCurrentView();
        void fetchStats();
    } catch (e) {
        console.error("Gagal batalkan check-in", e);
        showToast(e.message || "Gagal koneksi server");
    } finally {
        setButtonLoading(btn, false, "Batalkan Ambil Race Pack");
    }
}

async function doAttendance() {
    if (!activeOrderNumber) return;
    const btn = document.getElementById("btn-attendance");
    setButtonLoading(btn, true, "Memproses...");

    try {
        await fetchJson(`${API_BASE_URL}/api/registration/attendance`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ no_order: activeOrderNumber })
        });
        showToast("Absensi kehadiran tercatat!");
        void refreshCurrentView();
        void fetchStats();
    } catch (e) {
        console.error("Gagal absen", e);
        showToast(e.message || "Gagal koneksi server");
    } finally {
        setButtonLoading(btn, false, "Absen Hadir");
    }
}

async function doUndoAttendance() {
    if (!activeOrderNumber) return;
    if (!confirm("Batalkan status hadir untuk peserta ini?")) return;

    const btn = document.getElementById("btn-attendance");
    setButtonLoading(btn, true, "Memproses...");

    try {
        await fetchJson(`${API_BASE_URL}/api/registration/attendance/undo`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ no_order: activeOrderNumber })
        });
        showToast("Status hadir dibatalkan!");
        void refreshCurrentView();
        void fetchStats();
    } catch (e) {
        console.error("Gagal batalkan hadir", e);
        showToast(e.message || "Gagal koneksi server");
    } finally {
        setButtonLoading(btn, false, "Batalkan Status Hadir");
    }
}

async function refreshCurrentView() {
    if (!activeOrderNumber) return;
    try {
        const result = await fetchJson(`${API_BASE_URL}/api/registration/participant/${encodeURIComponent(activeOrderNumber)}`);
        showParticipantDetail(result.data);
    } catch (e) {
        console.error("Gagal refresh tampilan peserta", e);
    }
}

let allParticipantsData = [];

const LIST_COLS = 13;

let listSortKey = "order_number";
let listSortDir = "asc";

function statusBadge(status, doneValue) {
    const ok = String(status || "").trim().toLowerCase() === doneValue;
    return ok
        ? '<span class="badge bg-ngg-black">Sudah</span>'
        : '<span class="badge bg-ngg-white text-ngg-black" style="border:1px solid rgba(0,0,0,0.1)">Belum</span>';
}

function statusBadgeWithTime(status, doneValue, waktu) {
    const ok = String(status || "").trim().toLowerCase() === doneValue;
    if (!ok) {
        return '<span class="badge bg-ngg-white text-ngg-black" style="border:1px solid rgba(0,0,0,0.1)">Belum</span>';
    }
    const t = String(waktu || "").trim();
    return `<span class="badge bg-ngg-black text-nowrap">Sudah${t ? " (" + escapeHtml(t) + ")" : ""}</span>`;
}

async function loadAllParticipants() {
    const tbody = document.getElementById("alldata-body");
    const btn = document.querySelector("#tab-list .btn-outline-black");
    setButtonLoading(btn, true, "Memuat...");

    tbody.innerHTML = `<tr><td colspan="${LIST_COLS}" class="text-center py-3"><span class="btn-loading">Sedang mengambil data peserta...</span></td></tr>`;

    try {
        const res = await fetchJson(`${API_BASE_URL}/api/registration/participants`);

        if (res.data && res.data.length > 0) {
            allParticipantsData = res.data;
            renderListPeserta(res.data);
        } else {
            allParticipantsData = [];
            tbody.innerHTML = `<tr><td colspan="${LIST_COLS}" class="text-center py-3">Tidak ada data.</td></tr>`;
            document.getElementById("list-count").textContent = "";
        }
    } catch (e) {
        console.error("Gagal memuat peserta", e);
        tbody.innerHTML = `<tr><td colspan="${LIST_COLS}" class="text-center py-3 text-danger">Gagal menghubungi server.</td></tr>`;
        document.getElementById("list-count").textContent = "";
    } finally {
        setButtonLoading(btn, false, "Muat Ulang");
    }
}

async function syncFromSheet() {
    const btn = document.getElementById("btn-sync-sheet");
    if (!btn || btn.disabled) return;
    const icon = '<i class="bi bi-arrow-repeat"></i>';
    btn.disabled = true;
    btn.classList.add("btn-loading");
    btn.innerHTML = `${icon} Sync...`;
    try {
        const res = await fetchJson(`${API_BASE_URL}/api/registration/sync`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
        });
        showToast(res.message || `Sync selesai: ${res.total_peserta} peserta`);
        void fetchStats();
        const listPane = document.getElementById("tab-list");
        if (listPane && listPane.classList.contains("active")) {
            void loadAllParticipants();
        }
    } catch (e) {
        showToast(e.message || "Gagal sync dari Google Sheets");
    } finally {
        btn.disabled = false;
        btn.classList.remove("btn-loading");
        btn.innerHTML = `${icon} Sync Sheet`;
    }
}

function getSortValue(row, key) {
    if (key === "item_name") return row.item_name || row.paket || "";
    return row[key] ?? "";
}

function sortParticipantRows(rows) {
    const dir = listSortDir === "desc" ? -1 : 1;
    const key = listSortKey;
    return [...rows].sort((a, b) => {
        let av = getSortValue(a, key);
        let bv = getSortValue(b, key);
        if (key === "order_number") {
            const an = Number(av);
            const bn = Number(bv);
            if (!Number.isNaN(an) && !Number.isNaN(bn) && String(av).trim() !== "" && String(bv).trim() !== "") {
                return (an - bn) * dir;
            }
        }
        av = String(av).toLowerCase();
        bv = String(bv).toLowerCase();
        if (av < bv) return -1 * dir;
        if (av > bv) return 1 * dir;
        return 0;
    });
}

function updateListSortIndicators() {
    document.querySelectorAll("#tab-list thead th.sortable").forEach(th => {
        const icon = th.querySelector(".sort-icon");
        if (!icon) return;
        if (th.dataset.key === listSortKey) {
            icon.className = `sort-icon bi ${listSortDir === "asc" ? "bi-sort-up" : "bi-sort-down"}`;
            th.classList.add("sorted");
            th.setAttribute("aria-sort", listSortDir === "asc" ? "ascending" : "descending");
        } else {
            icon.className = "sort-icon bi bi-arrow-down-up";
            th.classList.remove("sorted");
            th.removeAttribute("aria-sort");
        }
    });
}

function toggleListSort(key) {
    if (listSortKey === key) {
        listSortDir = listSortDir === "asc" ? "desc" : "asc";
    } else {
        listSortKey = key;
        listSortDir = "asc";
    }
    updateListSortIndicators();
    filterListPeserta();
}

function renderListPeserta(data) {
    const tbody = document.getElementById("alldata-body");
    const countEl = document.getElementById("list-count");
    const sorted = sortParticipantRows(data);

    if (sorted.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${LIST_COLS}" class="text-center py-3">Data tidak ditemukan.</td></tr>`;
        countEl.textContent = "";
        return;
    }

    tbody.innerHTML = "";
    sorted.forEach(row => {
        const rp = statusBadgeWithTime(row.status_diambil, "sudah", row.waktu_diambil);
        const hd = statusBadgeWithTime(row.status_hadir, "hadir", row.waktu_hadir);

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td style="font-weight:600;" class="text-nowrap">${escapeHtml(row.order_number || "-")}</td>
            <td class="text-break-safe" style="min-width: 140px;">${escapeHtml(row.nama_lengkap_ibu || "-")}</td>
            <td class="text-break-safe" style="min-width: 140px;">${escapeHtml(row.nama_lengkap_ayah || "-")}</td>
            <td class="text-break-safe" style="min-width: 130px;">${escapeHtml(row.nama_anak || "-")}</td>
            <td class="text-nowrap">${escapeHtml(row.usia_bayi || "-")}</td>
            <td class="text-nowrap">${escapeHtml(row.nomor_wa || "-")}</td>
            <td class="text-break-safe" style="min-width: 160px;">${escapeHtml(row.email || "-")}</td>
            <td class="text-break-safe" style="min-width: 180px;">${escapeHtml(row.item_name || row.paket || "-")}</td>
            <td class="text-break-safe">${escapeHtml(row.uk_kaos_ibu || "-")}</td>
            <td class="text-break-safe">${escapeHtml(row.uk_kaos_ayah || "-")}</td>
            <td class="text-nowrap">${escapeHtml(row.order_status || "-")}</td>
            <td>${rp}</td>
            <td>${hd}</td>`;
        tbody.appendChild(tr);
    });

    countEl.textContent = `Menampilkan ${sorted.length} dari ${allParticipantsData.length} peserta`;
}

function filterListPeserta() {
    const keyword = document.getElementById("filter-list").value.trim().toLowerCase();
    if (!keyword) {
        renderListPeserta(allParticipantsData);
        return;
    }

    const filtered = allParticipantsData.filter(row => {
        const fields = [
            row.order_number, row.nama_lengkap_ibu, row.nama_lengkap_ayah,
            row.nama_anak, row.nomor_wa, row.email, row.item_name,
            row.paket, row.order_status, row.usia_bayi
        ];
        return fields.some(f => String(f || "").toLowerCase().includes(keyword));
    });

    renderListPeserta(filtered);
}

function resetView() {
    document.getElementById("result-container").classList.add("d-none");
    document.getElementById("search-results-container").classList.add("d-none");
    document.getElementById("placeholder-box").classList.remove("d-none");
    activeOrderNumber = "";
}

/* =========================
   AUTH / SESSION GATE
   ========================= */

function resetAppUI() {
    // Close any open modal
    const modalEl = document.getElementById("userModal");
    const modal = bootstrap.Modal.getInstance(modalEl);
    if (modal) modal.hide();

    // Main tabs → Input Peserta
    document.querySelectorAll("#pills-tab .nav-link").forEach(b => b.classList.remove("active"));
    document.getElementById("tab-input-btn")?.classList.add("active");
    document.querySelectorAll("#pills-tabContent .tab-pane").forEach(p => p.classList.remove("show", "active"));
    document.getElementById("tab-input")?.classList.add("show", "active");

    // Search & detail peserta
    activeOrderNumber = "";
    const searchInput = document.getElementById("search_keyword");
    if (searchInput) searchInput.value = "";
    document.getElementById("search-results-container")?.classList.add("d-none");
    const searchBody = document.getElementById("search-results-body");
    if (searchBody) searchBody.innerHTML = "";
    document.getElementById("result-container")?.classList.add("d-none");
    document.getElementById("placeholder-box")?.classList.remove("d-none");

    // List peserta
    allParticipantsData = [];
    listSortKey = "order_number";
    listSortDir = "asc";
    updateListSortIndicators();
    const filterList = document.getElementById("filter-list");
    if (filterList) filterList.value = "";
    const listBody = document.getElementById("alldata-body");
    if (listBody) listBody.innerHTML = "";
    const listCount = document.getElementById("list-count");
    if (listCount) listCount.textContent = "";

    // Backoffice (admin)
    adminSectionLoaded = {};
    auditOffset = 0;
    editingUserId = null;
    document.querySelectorAll("#admin-sub-nav .nav-link").forEach(b => b.classList.remove("active"));
    document.getElementById("admin-sub-users-btn")?.classList.add("active");
    document.querySelectorAll("#admin-sub-content .tab-pane").forEach(p => p.classList.remove("show", "active"));
    document.getElementById("admin-section-users")?.classList.add("show", "active");
    const usersBody = document.getElementById("admin-users-body");
    if (usersBody) usersBody.innerHTML = `<tr><td colspan="8" class="text-center py-3">Memuat...</td></tr>`;
    const auditBody = document.getElementById("audit-body");
    if (auditBody) auditBody.innerHTML = `<tr><td colspan="7" class="text-center py-3">Memuat...</td></tr>`;
    const auditCount = document.getElementById("audit-count");
    if (auditCount) auditCount.textContent = "";
    const auditPrev = document.getElementById("audit-prev");
    if (auditPrev) auditPrev.disabled = true;
    const auditNext = document.getElementById("audit-next");
    if (auditNext) auditNext.disabled = true;
    const auditAction = document.getElementById("audit-action-filter");
    if (auditAction) auditAction.value = "";
    const auditActor = document.getElementById("audit-actor-filter");
    if (auditActor) auditActor.value = "";
    const auditEntity = document.getElementById("audit-entity-filter");
    if (auditEntity) auditEntity.value = "";
    ["stat-users-total", "stat-users-active", "stat-logs-total", "stat-logs-today"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = "-";
    });
    const topActors = document.getElementById("top-actors-body");
    if (topActors) topActors.innerHTML = `<tr><td colspan="2" class="text-center py-3">Memuat...</td></tr>`;

    // Live stats akan di-refresh oleh fetchStats() saat showApp()
    const liveStats = document.getElementById("live-stats");
    if (liveStats) liveStats.textContent = "-";
}

function showLogin(message) {
    currentUser = null;
    resetAppUI();
    const shell = document.getElementById("app-shell");
    const login = document.getElementById("login-screen");
    if (shell) shell.classList.add("d-none");
    if (login) login.classList.remove("d-none");
    const boot = document.getElementById("login-boot-status");
    const form = document.getElementById("login-form");
    if (boot) boot.classList.add("d-none");
    if (form) form.classList.remove("d-none");
    const errEl = document.getElementById("login-error");
    if (errEl) {
        if (message) {
            errEl.textContent = message;
            errEl.classList.remove("d-none");
        } else {
            errEl.classList.add("d-none");
        }
    }
    const pw = document.getElementById("login-password");
    if (pw && message) pw.value = "";
}

function showApp(user) {
    currentUser = user;
    const login = document.getElementById("login-screen");
    const shell = document.getElementById("app-shell");
    if (login) login.classList.add("d-none");
    if (shell) shell.classList.remove("d-none");

    const usernameEl = document.getElementById("nav-username");
    const roleEl = document.getElementById("nav-role");
    if (usernameEl) usernameEl.textContent = user.username || "-";
    if (roleEl) {
        roleEl.textContent = user.role || "-";
        roleEl.classList.toggle("role-admin", user.role === "admin");
        roleEl.classList.toggle("role-staff", user.role !== "admin");
    }

    const adminItem = document.getElementById("tab-admin-item");
    if (adminItem) {
        adminItem.classList.toggle("d-none", user.role !== "admin");
    }

    const errEl = document.getElementById("login-error");
    if (errEl) errEl.classList.add("d-none");
    const pw = document.getElementById("login-password");
    if (pw) pw.value = "";

    void fetchStats();
}

async function bootApp() {
    try {
        const res = await fetchJson(`${API_BASE_URL}/api/auth/me`);
        if (res && res.user) {
            showApp(res.user);
            return;
        }
        showLogin();
    } catch (e) {
        if (e.status === 401) {
            showLogin();
        } else {
            showLogin(e.message || "Gagal memuat sesi. Periksa koneksi.");
        }
    }
}

async function doLogin(event) {
    if (event) event.preventDefault();
    const username = document.getElementById("login-username").value.trim();
    const password = document.getElementById("login-password").value;
    const errEl = document.getElementById("login-error");
    const btn = document.getElementById("btn-login");

    if (!username || !password) {
        if (errEl) {
            errEl.textContent = "Isi username dan password.";
            errEl.classList.remove("d-none");
        }
        return false;
    }

    setButtonLoading(btn, true, "Masuk...");
    try {
        const res = await fetchJson(`${API_BASE_URL}/api/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password }),
        });
        if (res && res.user) showApp(res.user);
    } catch (e) {
        if (errEl) {
            errEl.textContent = e.message || "Login gagal";
            errEl.classList.remove("d-none");
        }
    } finally {
        setButtonLoading(btn, false, "Masuk");
    }
    return false;
}

async function doLogout() {
    try {
        await fetchJson(`${API_BASE_URL}/api/auth/logout`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
        });
    } catch (e) {
        console.error("Logout error", e);
    }
    showLogin();
}

/* =========================
   BACKOFFICE (admin)
   ========================= */

let adminSectionLoaded = {};
let editingUserId = null;
let auditOffset = 0;
const AUDIT_LIMIT = 50;

function onAdminTabOpen() {
    if (!currentUser || currentUser.role !== "admin") return;
    if (!adminSectionLoaded.users) void loadAdminUsers();
    else if (!adminSectionLoaded.logs) void loadAuditLogs(true);
    else if (!adminSectionLoaded.stats) void loadAdminStats();
}

function onAdminSection(section) {
    if (!currentUser || currentUser.role !== "admin") return;
    if (section === "users" && !adminSectionLoaded.users) void loadAdminUsers();
    if (section === "logs" && !adminSectionLoaded.logs) void loadAuditLogs(true);
    if (section === "stats" && !adminSectionLoaded.stats) void loadAdminStats();
}

async function loadAdminUsers() {
    const tbody = document.getElementById("admin-users-body");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="8" class="text-center py-3">Memuat...</td></tr>`;
    try {
        const res = await fetchJson(`${API_BASE_URL}/api/admin/users`);
        const rows = res.data || [];
        adminSectionLoaded.users = true;
        if (rows.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-3">Belum ada user.</td></tr>`;
            return;
        }
        tbody.innerHTML = "";
        rows.forEach(u => {
            const active = !!u.is_active;
            const roleBadge = u.role === "admin"
                ? '<span class="badge bg-ngg-blue text-nowrap">admin</span>'
                : '<span class="badge bg-ngg-white text-ngg-black text-nowrap" style="border:1px solid rgba(0,0,0,0.15)">staff</span>';
            const statusBadge = active
                ? '<span class="badge bg-ngg-black">Aktif</span>'
                : '<span class="badge" style="background:#b00020;color:#fff">Nonaktif</span>';
            const isSelf = currentUser && u.id === currentUser.id;
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${escapeHtml(String(u.id))}</td>
                <td class="text-nowrap" style="font-weight:600;">${escapeHtml(u.username || "-")}${isSelf ? ' <span class="badge bg-ngg-white text-ngg-black" style="border:1px solid rgba(0,0,0,0.15)">Anda</span>' : ""}</td>
                <td>${roleBadge}</td>
                <td>${statusBadge}</td>
                <td>${escapeHtml(String(u.failed_login_count ?? 0))}</td>
                <td class="text-nowrap">${escapeHtml(u.locked_until || "-")}</td>
                <td class="text-nowrap">${escapeHtml(String(u.created_at || "-").replace("T", " ").slice(0, 19))}</td>
                <td class="text-nowrap text-center">
                    <button class="btn btn-sm btn-outline-black me-1" type="button" data-edit-user="${u.id}"><i class="bi bi-pencil"></i></button>
                    ${isSelf ? "" : `<button class="btn btn-sm ${active ? "btn-undo" : "btn-blue"}" type="button" data-toggle-user="${u.id}" data-active="${active ? 0 : 1}">${active ? "Nonaktifkan" : "Aktifkan"}</button>`}
                </td>`;
            tr.querySelector("[data-edit-user]").addEventListener("click", () => openEditUser(u));
            const toggleBtn = tr.querySelector("[data-toggle-user]");
            if (toggleBtn) {
                toggleBtn.addEventListener("click", () => toggleUserActive(
                    Number(toggleBtn.dataset.toggleUser),
                    toggleBtn.dataset.active === "1"
                ));
            }
            tbody.appendChild(tr);
        });
    } catch (e) {
        if (e.status !== 401) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-3 text-danger">${escapeHtml(e.message || "Gagal memuat user")}</td></tr>`;
        }
    }
}

function openCreateUser() {
    editingUserId = null;
    document.getElementById("userModalTitle").textContent = "Tambah User";
    document.getElementById("user-edit-id").value = "";
    const usernameInput = document.getElementById("user-username");
    usernameInput.value = "";
    usernameInput.disabled = false;
    document.getElementById("user-role").value = "staff";
    document.getElementById("user-password").value = "";
    document.getElementById("user-password").required = true;
    document.getElementById("user-active").checked = true;
    document.getElementById("user-active").disabled = false;
    document.getElementById("user-modal-error").classList.add("d-none");
    bootstrap.Modal.getOrCreateInstance(document.getElementById("userModal")).show();
}

function openEditUser(u) {
    editingUserId = u.id;
    document.getElementById("userModalTitle").textContent = "Edit User";
    document.getElementById("user-edit-id").value = String(u.id);
    const usernameInput = document.getElementById("user-username");
    usernameInput.value = u.username || "";
    usernameInput.disabled = true;
    document.getElementById("user-role").value = u.role === "admin" ? "admin" : "staff";
    document.getElementById("user-password").value = "";
    document.getElementById("user-password").required = false;
    document.getElementById("user-active").checked = !!u.is_active;
    document.getElementById("user-active").disabled = currentUser && u.id === currentUser.id;
    document.getElementById("user-modal-error").classList.add("d-none");
    bootstrap.Modal.getOrCreateInstance(document.getElementById("userModal")).show();
}

async function saveUser() {
    const errEl = document.getElementById("user-modal-error");
    const btn = document.getElementById("btn-save-user");
    errEl.classList.add("d-none");

    const isCreate = !editingUserId;
    const username = document.getElementById("user-username").value.trim();
    const role = document.getElementById("user-role").value;
    const password = document.getElementById("user-password").value;
    const isActive = document.getElementById("user-active").checked;

    if (isCreate && (!username || username.length < 3)) {
        errEl.textContent = "Username min. 3 karakter.";
        errEl.classList.remove("d-none");
        return;
    }
    if ((isCreate || password) && (!password || password.length < 8)) {
        errEl.textContent = "Password min. 6 karakter.";
        errEl.classList.remove("d-none");
        return;
    }

    setButtonLoading(btn, true, "Menyimpan...");
    try {
        if (isCreate) {
            await fetchJson(`${API_BASE_URL}/api/admin/users`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password, role }),
            });
            showToast(`User "${username}" dibuat`);
        } else {
            const body = { role };
            if (password) body.password = password;
            if (!(currentUser && editingUserId === currentUser.id)) body.is_active = isActive;
            await fetchJson(`${API_BASE_URL}/api/admin/users/${editingUserId}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            showToast("User diperbarui");
        }
        bootstrap.Modal.getInstance(document.getElementById("userModal"))?.hide();
        void loadAdminUsers();
    } catch (e) {
        errEl.textContent = e.message || "Gagal menyimpan";
        errEl.classList.remove("d-none");
    } finally {
        setButtonLoading(btn, false, "Simpan");
    }
}

async function toggleUserActive(userId, activate) {
    if (!confirm(activate ? "Aktifkan akun ini?" : "Nonaktifkan akun ini?")) return;
    try {
        await fetchJson(`${API_BASE_URL}/api/admin/users/${userId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ is_active: activate }),
        });
        showToast(activate ? "Akun diaktifkan" : "Akun dinonaktifkan");
        void loadAdminUsers();
    } catch (e) {
        showToast(e.message || "Gagal memperbarui akun");
    }
}

async function loadAuditLogs(reset) {
    if (reset) auditOffset = 0;
    const tbody = document.getElementById("audit-body");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-3">Memuat...</td></tr>`;

    const action = document.getElementById("audit-action-filter").value.trim();
    const actor = document.getElementById("audit-actor-filter").value.trim();
    const entityId = document.getElementById("audit-entity-filter").value.trim();
    const params = new URLSearchParams({
        limit: String(AUDIT_LIMIT),
        offset: String(auditOffset),
    });
    if (action) params.set("action", action);
    if (actor) params.set("actor", actor);
    if (entityId) params.set("entity_id", entityId);

    try {
        const res = await fetchJson(`${API_BASE_URL}/api/admin/audit?${params.toString()}`);
        adminSectionLoaded.logs = true;
        const items = res.items || [];
        const total = res.total || 0;

        if (items.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-3">Tidak ada log.</td></tr>`;
        } else {
            tbody.innerHTML = "";
            items.forEach(row => {
                const actionBadge = String(row.action || "").includes("fail") || String(row.action || "").includes("failed")
                    ? `<span class="badge" style="background:#b00020;color:#fff">${escapeHtml(row.action || "-")}</span>`
                    : `<span class="badge bg-ngg-black text-nowrap">${escapeHtml(row.action || "-")}</span>`;
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td class="text-nowrap">${escapeHtml(String(row.ts || "").replace("T", " ").slice(0, 19))}</td>
                    <td class="text-nowrap">${escapeHtml(row.actor_username || "-")}</td>
                    <td>${actionBadge}</td>
                    <td class="text-nowrap">${escapeHtml(row.entity || "-")}</td>
                    <td class="text-nowrap">${escapeHtml(row.entity_id || "-")}</td>
                    <td class="text-break-safe" style="min-width:140px;">${escapeHtml(row.detail || "")}</td>
                    <td class="text-nowrap">${escapeHtml(row.ip || "-")}</td>`;
                tbody.appendChild(tr);
            });
        }

        const from = total === 0 ? 0 : auditOffset + 1;
        const to = Math.min(auditOffset + items.length, total);
        document.getElementById("audit-count").textContent =
            items.length ? `Menampilkan ${from}-${to} dari ${total}` : `Total ${total} log`;
        document.getElementById("audit-prev").disabled = auditOffset <= 0;
        document.getElementById("audit-next").disabled = auditOffset + AUDIT_LIMIT >= total;
    } catch (e) {
        if (e.status !== 401) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-3 text-danger">${escapeHtml(e.message || "Gagal memuat log")}</td></tr>`;
            document.getElementById("audit-count").textContent = "";
            document.getElementById("audit-prev").disabled = true;
            document.getElementById("audit-next").disabled = true;
        }
    }
}

function auditPage(delta) {
    const next = auditOffset + delta * AUDIT_LIMIT;
    if (next < 0) return;
    auditOffset = next;
    void loadAuditLogs(false);
}

async function loadAdminStats() {
    try {
        const res = await fetchJson(`${API_BASE_URL}/api/admin/stats`);
        adminSectionLoaded.stats = true;
        const a = res.admin || {};
        document.getElementById("stat-users-total").textContent = a.users_total ?? "-";
        document.getElementById("stat-users-active").textContent = a.users_active ?? "-";
        document.getElementById("stat-logs-total").textContent = a.logs_total ?? "-";
        document.getElementById("stat-logs-today").textContent = a.logs_today ?? "-";

        const tbody = document.getElementById("top-actors-body");
        const top = a.top_actors_today || [];
        if (top.length === 0) {
            tbody.innerHTML = `<tr><td colspan="2" class="text-center py-3">Belum ada aktivitas hari ini.</td></tr>`;
        } else {
            tbody.innerHTML = "";
            top.forEach(row => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${escapeHtml(row.actor_username || "-")}</td>
                    <td class="text-end" style="font-weight:600;">${escapeHtml(String(row.count ?? 0))}</td>`;
                tbody.appendChild(tr);
            });
        }
    } catch (e) {
        if (e.status !== 401) showToast(e.message || "Gagal memuat statistik admin");
    }
}
