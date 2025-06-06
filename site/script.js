const data = [
  {
    title: "コンテンツ生成",
    category: "マーケティング",
    description: "ブログ記事や広告コピーの生成",
    keywords: ["文章生成", "広告", "コピー"]
  },
  {
    title: "画像生成",
    category: "デザイン",
    description: "プロモーション用画像の自動作成",
    keywords: ["画像", "プロモーション"]
  },
  {
    title: "コード補完",
    category: "開発支援",
    description: "コードの自動補完と説明",
    keywords: ["プログラミング", "補完"]
  }
];

function populateCategories() {
  const set = new Set(data.map(d => d.category));
  const select = document.getElementById('categorySelect');
  set.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c;
    opt.textContent = c;
    select.appendChild(opt);
  });
}

function search() {
  const category = document.getElementById('categorySelect').value;
  const keyword = document.getElementById('keywordInput').value.toLowerCase();
  const tbody = document.querySelector('#results tbody');
  tbody.innerHTML = '';

  data
    .filter(d => (!category || d.category === category) &&
                 (!keyword || d.keywords.some(k => k.includes(keyword)) || d.title.includes(keyword) || d.description.includes(keyword)))
    .forEach(d => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${d.title}</td><td>${d.category}</td><td>${d.description}</td>`;
      tbody.appendChild(tr);
    });
}

document.getElementById('searchButton').addEventListener('click', search);
window.addEventListener('load', () => {
  populateCategories();
  search();
});
