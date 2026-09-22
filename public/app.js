const API_BASE_URL = "";
let activeOrderNumber = "";

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

window.addEventListener("load", fetchStats);

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
        btnRp.disabled = true;
        btnRp.className = "btn btn-outline-black flex-grow-1 disabled";
        btnRp.textContent = "Telah Diambil";
    } else {
        badgeRp.className = "badge bg-ngg-white text-ngg-black fs-6 text-break-safe mt-1";
        badgeRp.style.border = "1px solid rgba(0,0,0,0.1)";
        badgeRp.textContent = "BELUM";
        btnRp.disabled = false;
        btnRp.className = "btn btn-black flex-grow-1";
        btnRp.textContent = "Ambil Race Pack";
    }

    const statusHadir = String(data.status_hadir || "").trim().toLowerCase();
    const badgeHadir = document.getElementById("res-status-hadir");
    const btnHadir = document.getElementById("btn-attendance");

    if (statusHadir === "hadir") {
        badgeHadir.className = "badge bg-ngg-black fs-6 text-break-safe mt-1";
        badgeHadir.textContent = "SUDAH (" + (data.waktu_hadir || "") + ")";
        btnHadir.disabled = true;
        btnHadir.className = "btn btn-outline-black flex-grow-1 disabled";
        btnHadir.textContent = "Telah Hadir";
    } else {
        badgeHadir.className = "badge bg-ngg-white text-ngg-black fs-6 text-break-safe mt-1";
        badgeHadir.style.border = "1px solid rgba(0,0,0,0.1)";
        badgeHadir.textContent = "BELUM";
        btnHadir.disabled = false;
        btnHadir.className = "btn btn-blue flex-grow-1";
        btnHadir.textContent = "Absen Hadir";
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

async function loadAllParticipants() {
    const tbody = document.getElementById("alldata-body");
    const btn = document.querySelector("#tab-list .btn-outline-black");
    setButtonLoading(btn, true, "Memuat...");

    tbody.innerHTML = `<tr><td colspan="6" class="text-center py-3"><span class="btn-loading">Sedang mengambil data peserta...</span></td></tr>`;

    try {
        const res = await fetchJson(`${API_BASE_URL}/api/registration/participants`);

        if (res.data && res.data.length > 0) {
            allParticipantsData = res.data;
            renderListPeserta(res.data);
        } else {
            allParticipantsData = [];
            tbody.innerHTML = `<tr><td colspan="6" class="text-center py-3">Tidak ada data.</td></tr>`;
            document.getElementById("list-count").textContent = "";
        }
    } catch (e) {
        console.error("Gagal memuat peserta", e);
        tbody.innerHTML = `<tr><td colspan="6" class="text-center py-3 text-danger">Gagal menghubungi server.</td></tr>`;
        document.getElementById("list-count").textContent = "";
    } finally {
        setButtonLoading(btn, false, "Muat Ulang");
    }
}

function renderListPeserta(data) {
    const tbody = document.getElementById("alldata-body");
    const countEl = document.getElementById("list-count");

    if (data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center py-3">Data tidak ditemukan.</td></tr>`;
        countEl.textContent = "";
        return;
    }

    tbody.innerHTML = "";
    data.forEach(row => {
        const rp = String(row.status_diambil || "").trim().toLowerCase() === "sudah" ?
            '<span class="badge bg-ngg-black">Sudah</span>' :
            '<span class="badge bg-ngg-white text-ngg-black" style="border:1px solid rgba(0,0,0,0.1)">Belum</span>';

        const hd = String(row.status_hadir || "").trim().toLowerCase() === "hadir" ?
            '<span class="badge bg-ngg-black">Sudah</span>' :
            '<span class="badge bg-ngg-white text-ngg-black" style="border:1px solid rgba(0,0,0,0.1)">Belum</span>';

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td style="font-weight:600;">${escapeHtml(row.order_number || "-")}</td>
            <td class="text-break-safe" style="min-width: 130px;">${escapeHtml(row.nama_lengkap_ibu || "-")}</td>
            <td class="text-break-safe" style="min-width: 130px;">${escapeHtml(row.nama_anak || "-")}</td>
            <td>${escapeHtml(row.order_status || "-")}</td>
            <td>${rp}</td>
            <td>${hd}</td>`;
        tbody.appendChild(tr);
    });

    countEl.textContent = `Menampilkan ${data.length} dari ${allParticipantsData.length} peserta`;
}

function filterListPeserta() {
    const keyword = document.getElementById("filter-list").value.trim().toLowerCase();
    if (!keyword) {
        renderListPeserta(allParticipantsData);
        return;
    }

    const filtered = allParticipantsData.filter(row => {
        const order = String(row.order_number || "").toLowerCase();
        const nama = String(row.nama_lengkap_ibu || "").toLowerCase();
        const anak = String(row.nama_anak || "").toLowerCase();
        return order.includes(keyword) || nama.includes(keyword) || anak.includes(keyword);
    });

    renderListPeserta(filtered);
}

function resetView() {
    document.getElementById("result-container").classList.add("d-none");
    document.getElementById("search-results-container").classList.add("d-none");
    document.getElementById("placeholder-box").classList.remove("d-none");
    activeOrderNumber = "";
}
