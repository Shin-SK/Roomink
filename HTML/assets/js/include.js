/**
 * Roomink Partials Loader
 * data-include属性で指定されたHTMLを読み込む
 */
document.addEventListener('DOMContentLoaded', async function() {
  console.log('[Partials] DOM loaded, starting to load partials...');
  
  async function loadPartial(el, url) {
    try {
      console.log(`[Partials] Loading: ${url}`);
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
      const content = await res.text();
      el.innerHTML = content;
      console.log(`[Partials] ✓ Loaded: ${url}`);
    } catch (err) {
      console.error(`[Partials] Error loading partial: ${url}`, err);
      el.innerHTML = `<!-- Error loading ${url} -->`;
    }
  }

  // data-include属性を持つ要素を全て取得
  const includeElements = Array.from(document.querySelectorAll('[data-include]'));
  console.log(`[Partials] Found ${includeElements.length} elements to load`);
  
  if (includeElements.length === 0) {
    console.warn('[Partials] No elements with data-include found!');
    return;
  }
  
  // 並列で全てのパーシャルを読み込む
  await Promise.all(
    includeElements.map(el => loadPartial(el, el.getAttribute('data-include')))
  );

  console.log('[Partials] All partials loaded, firing event');
  
  // 読み込み完了後のイベントを発火
  document.dispatchEvent(new Event('partials:loaded'));

  // ナビゲーションのアクティブ状態を設定
  setActiveNav();
});

/**
 * 現在のページに応じてナビゲーションのactiveクラスを設定
 */
function setActiveNav() {
  const currentPage = document.body.getAttribute('data-page');
  if (!currentPage) return;

  // サイドバーのリンク
  document.querySelectorAll('.sidebar .nav-link[data-page]').forEach(link => {
    if (link.getAttribute('data-page') === currentPage) {
      link.classList.add('active');
    }
  });

  // カスタマー/キャストヘッダーのリンク
  document.querySelectorAll('.customer-nav a[data-page]').forEach(link => {
    if (link.getAttribute('data-page') === currentPage) {
      link.classList.add('active');
    }
  });
}
