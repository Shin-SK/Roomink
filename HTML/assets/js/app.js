// Roomink - 最小限のJavaScript

// パーシャルが読み込まれた後に初期化
document.addEventListener('partials:loaded', function() {
  initActiveNav();
  initMobileMenu();
  initConfirmButtons();
  initScheduleToolbarToggle();
  initDashboardTabs();
  initCustomerSearchToggle();
  initShiftTabs();
  initRoomTabs();
  initBottomNav();
  initMypageTabs();
  initNotificationBell();
});

// パーシャルを使わないページのためのフォールバック
document.addEventListener('DOMContentLoaded', function() {
  // sidebar要素が既に存在する場合（パーシャル未使用ページ）
  if (document.querySelector('.sidebar')) {
    initActiveNav();
    initMobileMenu();
    initConfirmButtons();
    initScheduleToolbarToggle();
    initDashboardTabs();
    initCustomerSearchToggle();
    initShiftTabs();
    initRoomTabs();
    initBottomNav();
    initMypageTabs();
  }
});

/**
 * 現在ページのナビゲーションをアクティブにする
 */
function initActiveNav() {
  const currentPath = window.location.pathname;
  const fileName = currentPath.split('/').pop() || 'index.html';

  // サイドバーナビ
  const navLinks = document.querySelectorAll('.nav-link');
  navLinks.forEach(link => {
    const href = link.getAttribute('href');
    if (href === fileName || (fileName === '' && href === 'index.html')) {
      link.classList.add('active');
    }
  });

  // 顧客用ナビ
  const customerNavLinks = document.querySelectorAll('.customer-nav a');
  customerNavLinks.forEach(link => {
    const href = link.getAttribute('href');
    if (href === fileName) {
      link.classList.add('active');
    }
  });
}

/**
 * モバイルメニューの開閉
 */
function initMobileMenu() {
  const menuBtn = document.querySelector('.mobile-menu-btn');
  const sidebar = document.querySelector('.sidebar');

  if (menuBtn && sidebar) {
    menuBtn.addEventListener('click', () => {
      sidebar.classList.toggle('show');
    });

    // サイドバー外をクリックで閉じる
    document.addEventListener('click', (e) => {
      if (sidebar.classList.contains('show') &&
          !sidebar.contains(e.target) &&
          !menuBtn.contains(e.target)) {
        sidebar.classList.remove('show');
      }
    });

    // ナビリンクをクリックしたら閉じる（モバイル）
    const navLinks = document.querySelectorAll('.nav-link');
    navLinks.forEach(link => {
      link.addEventListener('click', () => {
        if (window.innerWidth < 992) {
          sidebar.classList.remove('show');
        }
      });
    });
  }
}

/**
 * 確認ダイアログ付きボタン
 */
function initConfirmButtons() {
  const confirmBtns = document.querySelectorAll('[data-confirm]');

  confirmBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
      const message = btn.getAttribute('data-confirm');
      if (!confirm(message)) {
        e.preventDefault();
        return false;
      }
    });
  });
}

/**
 * スケジュールページのツールバートグル
 */
function initScheduleToolbarToggle() {
  const toggleBtn = document.getElementById('toolbar-toggle');
  const toolbarMenu = document.getElementById('toolbar-menu');

  if (!toggleBtn || !toolbarMenu) return;

  // ボタンクリックでトグル
  toggleBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    toolbarMenu.classList.toggle('d-none');
  });

  // メニュー外をクリックで閉じる
  document.addEventListener('click', (e) => {
    if (!toolbarMenu.classList.contains('d-none') &&
        !toolbarMenu.contains(e.target) &&
        !toggleBtn.contains(e.target)) {
      toolbarMenu.classList.add('d-none');
    }
  });

  // 凡例トグル（ツールバーメニュー内）
  const legendToggleMenu = document.getElementById('legend-toggle-menu');
  const legendContentMenu = document.getElementById('legend-content-menu');

  if (legendToggleMenu && legendContentMenu) {
    legendToggleMenu.addEventListener('click', (e) => {
      e.stopPropagation();
      legendContentMenu.classList.toggle('d-none');
      const isVisible = !legendContentMenu.classList.contains('d-none');
      legendToggleMenu.innerHTML = isVisible 
        ? '<i class="ti ti-info-circle me-1"></i>凡例を非表示'
        : '<i class="ti ti-info-circle me-1"></i>凡例を表示';
    });
  }

  // 凡例トグル（ページ下部）
  const legendTogglePage = document.getElementById('legend-toggle-page');
  const legendContentPage = document.getElementById('legend-content-page');

  if (legendTogglePage && legendContentPage) {
    legendTogglePage.addEventListener('click', (e) => {
      e.stopPropagation();
      legendContentPage.classList.toggle('d-none');
      const isVisible = !legendContentPage.classList.contains('d-none');
      legendTogglePage.innerHTML = isVisible 
        ? '<i class="ti ti-info-circle me-1"></i>凡例を非表示'
        : '<i class="ti ti-info-circle me-1"></i>凡例を表示';
    });
  }
}

/**ダッシュボードのタブ切り替え
 */
function initDashboardTabs() {
  const tabButtons = document.querySelectorAll('[data-tab]');
  
  if (tabButtons.length === 0) return;

  tabButtons.forEach(button => {
    button.addEventListener('click', () => {
      const targetTab = button.dataset.tab;
      
      // すべてのボタンからactiveクラスを削除
      tabButtons.forEach(btn => btn.classList.remove('active'));
      
      // クリックされたボタンにactiveクラスを追加
      button.classList.add('active');
      
      // すべてのタブコンテンツを非表示
      document.getElementById('mikakunin')?.classList.add('d-none');
      document.getElementById('kakunin')?.classList.add('d-none');
      
      // 対象のタブコンテンツを表示
      document.getElementById(targetTab)?.classList.remove('d-none');
    });
  });
}

/**
 * 顧客検索フィルタのトグル
 */
function initCustomerSearchToggle() {
  const toggleBtn = document.getElementById('customer-search-toggle');
  const panel = document.getElementById('customer-search-panel');

  if (!toggleBtn || !panel) return;

  toggleBtn.addEventListener('click', () => {
    panel.classList.toggle('d-none');
  });
}

/**
 * シフトページのタブ切り替え
 */
function initShiftTabs() {
  const tabButtons = document.querySelectorAll('[data-tab^="shift-"]');
  if (tabButtons.length === 0) return;

  tabButtons.forEach(button => {
    button.addEventListener('click', () => {
      const targetTab = button.dataset.tab;

      tabButtons.forEach(btn => btn.classList.remove('active'));
      button.classList.add('active');

      document.getElementById('shift-create')?.classList.add('d-none');
      document.getElementById('shift-list')?.classList.add('d-none');

      document.getElementById(targetTab)?.classList.remove('d-none');
    });
  });
}

/**
 * ルームページのタブ切り替え
 */
function initRoomTabs() {
  const tabButtons = document.querySelectorAll('[data-tab^="room-"]');
  if (tabButtons.length === 0) return;

  tabButtons.forEach(button => {
    button.addEventListener('click', () => {
      const targetTab = button.dataset.tab;

      tabButtons.forEach(btn => btn.classList.remove('active'));
      button.classList.add('active');

      document.getElementById('room-view')?.classList.add('d-none');
      document.getElementById('room-info')?.classList.add('d-none');

      document.getElementById(targetTab)?.classList.remove('d-none');
    });
  });
}

/**
 * 
 * 予約ブロックをクリックした時の処理
 */
function onBookingBlockClick(orderId) {
  window.location.href = `op_order.html?id=${orderId}`;
}

/**
 * フォーム送信時の処理（顧客予約フォーム）
 */
function handleBookingSubmit(e) {
  e.preventDefault();

  const form = e.target;
  const formData = new FormData(form);

  // バリデーション
  const phone = formData.get('phone');
  if (!phone || phone.length < 10) {
    alert('電話番号を正しく入力してください');
    return false;
  }

  // 実際のプロダクトではAPIにPOST
  console.log('予約申請送信:', Object.fromEntries(formData));

  // 完了ページへ遷移
  window.location.href = 'cu_submitted.html';
  return false;
}

/**
 * 電話番号検索（運営用）
 */
function searchByPhone() {
  const phoneInput = document.querySelector('#phone-search');
  if (!phoneInput) return;

  const phone = phoneInput.value.trim();
  if (phone.length < 10) {
    alert('電話番号を10桁以上で入力してください');
    return;
  }

  console.log('電話番号検索:', phone);

  // デモ用：顧客情報を表示
  const resultDiv = document.querySelector('#customer-result');
  if (resultDiv) {
    resultDiv.innerHTML = `
      <div class="card">
        <div class="card-body">
          <h5>田中 太郎</h5>
          <p class="text-muted mb-2">電話: ${phone}</p>
          <p class="mb-2">前回来店: 2025-01-15</p>
          <p class="mb-2">来店回数: 5回</p>
          <span class="badge badge-approved">通常</span>
          <hr>
          <button class="btn btn-primary btn-sm" onclick="selectCustomer('${phone}')">この顧客で予約作成</button>
        </div>
      </div>
    `;
  }
}

/**
 * 顧客選択（電話予約用）
 */
function selectCustomer(phone) {
  console.log('顧客選択:', phone);
  const step2 = document.querySelector('#booking-step');
  if (step2) {
    step2.style.display = 'block';
    step2.scrollIntoView({ behavior: 'smooth' });
  }
}

/**
 * 承認ボタンクリック
 */
function approveOrder(orderId) {
  if (!confirm('この予約を承認しますか？')) return;

  console.log('承認:', orderId);
  alert('予約を承認しました');

  // リストから削除（デモ用）
  const item = document.querySelector(`[data-order-id="${orderId}"]`);
  if (item) {
    item.style.opacity = '0.5';
    setTimeout(() => item.remove(), 300);
  }
}

/**
 * 否認ボタンクリック
 */
function rejectOrder(orderId) {
  const reason = prompt('否認理由を入力してください:');
  if (!reason) return;

  console.log('否認:', orderId, reason);
  alert('予約を否認しました');

  // リストから削除（デモ用）
  const item = document.querySelector(`[data-order-id="${orderId}"]`);
  if (item) {
    item.style.opacity = '0.5';
    setTimeout(() => item.remove(), 300);
  }
}

/**
 * 確認ボタンクリック（キャスト用）
 */
function confirmReservation(orderId) {
  if (!confirm('この予約を確認しましたか？')) return;

  console.log('確認済:', orderId);

  // 未確認バッジを削除
  const item = document.querySelector(`[data-order-id="${orderId}"]`);
  if (item) {
    const badge = item.querySelector('.badge-unconfirmed');
    if (badge) badge.remove();

    // 背景色を戻す
    item.style.background = '';

    // ボタンを無効化
    const btn = item.querySelector('button');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '確認済';
      btn.classList.remove('btn-warning');
      btn.classList.add('btn-outline');
    }
  }
}

/**
 * Customer Bottom Nav のアクティブ状態
 */
function initBottomNav() {
  const nav = document.querySelector('.rk-bottomnav');
  if (!nav) return;

  const currentPath = window.location.pathname.split('/').pop() || 'index.html';
  const hash = window.location.hash;

  nav.querySelectorAll('.rk-bottomnav__item').forEach(item => {
    const href = item.getAttribute('href');
    const page = item.dataset.page;
    if (href === currentPath || (page && currentPath.includes(page.replace('mypage', 'cu_mypage').replace('booking', 'cu_booking')))) {
      // #fav リンクはハッシュ一致時のみ active
      if (href.includes('#') && hash !== href.split(currentPath).pop()) return;
      if (!href.includes('#')) item.classList.add('active');
    }
  });
}

/**
 * マイページのタブ切り替え（推し / おすすめ / 運営おすすめ）
 */
function initMypageTabs() {
  const tabs = document.querySelectorAll('.rk-tabs__btn');
  if (tabs.length === 0) return;

  tabs.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.rkTab;
      if (!target) return;

      // ボタン active 切り替え
      tabs.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      // パネル表示切り替え
      const parent = btn.closest('.rk-tabs')?.parentElement;
      if (!parent) return;
      parent.querySelectorAll('[data-rk-panel]').forEach(p => p.classList.add('d-none'));
      const panel = parent.querySelector(`[data-rk-panel="${target}"]`);
      if (panel) panel.classList.remove('d-none');
    });
  });

  // URL ハッシュが #fav なら推しタブを選択
  if (window.location.hash === '#fav') {
    const favBtn = document.querySelector('.rk-tabs__btn[data-rk-tab="fav"]');
    if (favBtn) favBtn.click();
  }
}

/**
 * 通知ベルの開閉
 */
function initNotificationBell() {
  const bell = document.getElementById('notification-bell');
  const dropdown = document.getElementById('notification-dropdown');

  if (!bell || !dropdown) return;

  bell.addEventListener('click', (e) => {
    e.stopPropagation();
    dropdown.classList.toggle('is-open');
  });

  // ドロップダウン内クリックは閉じない
  dropdown.addEventListener('click', (e) => {
    e.stopPropagation();
  });

  // 外側クリックで閉じる
  document.addEventListener('click', () => {
    dropdown.classList.remove('is-open');
  });
}

/**
 * すべて既読にする
 */
function markAllRead(e) {
  e.stopPropagation();
  const items = document.querySelectorAll('.notification-dropdown__item.is-unread');
  items.forEach(item => item.classList.remove('is-unread'));

  // カウントバッジを非表示
  const count = document.querySelector('.header-bell .count');
  if (count) count.style.display = 'none';
}

// グローバルスコープに公開
window.onBookingBlockClick = onBookingBlockClick;
window.handleBookingSubmit = handleBookingSubmit;
window.searchByPhone = searchByPhone;
window.selectCustomer = selectCustomer;
window.approveOrder = approveOrder;
window.rejectOrder = rejectOrder;
window.confirmReservation = confirmReservation;
window.markAllRead = markAllRead;

/**
 * Roomink schedule: place .rk-block by data-col / data-start / data-end
 */
(function () {
  function parseTimeToMin(t) {
    // "13:30" -> minutes
    const [h, m] = String(t).split(":").map(Number);
    return h * 60 + m;
  }

  function getCssVarPx(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const n = parseFloat(v);
    return Number.isFinite(n) ? n : fallback;
  }

  function layoutRoominkSheet(sheetEl) {
    const grid = sheetEl.querySelector(".rk-grid");
    if (!grid) return;

    const cols = Number(sheetEl.dataset.cols || grid.dataset.cols || 1);
    const start = sheetEl.dataset.start || "12:00";
    const end = sheetEl.dataset.end || "20:00";

    const startMin = parseTimeToMin(start);
    const endMin = parseTimeToMin(end);

    const colW = getCssVarPx("--rk-col-w", 120);
    const hourH = getCssVarPx("--rk-row-hour-h", 80);

    // 行数：12:00〜20:00 を「9行」にしたいなら +1 する
    // 例) 12〜20 は 8時間差だが表示は 12,13,...,20 の9行
    const hourSpan = Math.max(1, Math.round((endMin - startMin) / 60));
    const rows = hourSpan + 1;

    // グリッドサイズ確定
    grid.style.minWidth = `${colW * cols}px`;
    grid.style.height = `${hourH * rows}px`;

    // ブロック配置
    grid.querySelectorAll(".rk-block").forEach((el) => {
      const col = Number(el.dataset.col || 0);
      const s = parseTimeToMin(el.dataset.start);
      const e = parseTimeToMin(el.dataset.end);

      // 12:00を0として上から積む
      const top = ((s - startMin) / 60) * hourH;
      const height = Math.max(24, ((e - s) / 60) * hourH);

      const paddingX = 8;
      const left = col * colW + paddingX;
      const width = colW - paddingX * 2;

      el.style.top = `${top + 6}px`;
      el.style.left = `${left}px`;
      el.style.width = `${width}px`;
      el.style.height = `${height - 12}px`;
    });
  }

  function layoutAll() {
    document.querySelectorAll(".rk-sheet").forEach(layoutRoominkSheet);
  }

  window.addEventListener("load", layoutAll);
  window.addEventListener("resize", layoutAll);

  // include.js を使っている場合の保険（partialsが読み込まれたら再レイアウト）
  document.addEventListener("partials:loaded", layoutAll);
})();
