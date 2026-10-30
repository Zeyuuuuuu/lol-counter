/* LOL counter 速查 — 纯静态，无外部请求 */
(function () {
  "use strict";

  var CHAMPS = (window.__CHAMPIONS__ && window.__CHAMPIONS__.champions) || {};
  var META = window.__COUNTERS__ ? window.__COUNTERS__.meta : {};
  var DATA = window.__COUNTERS__ ? window.__COUNTERS__.data : {};
  var BUILDS = window.__BUILDS__ ? window.__BUILDS__.data : {};
  var DUOS = window.__DUOS__ || null;

  var LANES = [
    ["top", "上"], ["jungle", "野"], ["middle", "中"],
    ["bottom", "下"], ["support", "辅"]
  ];
  var DIMS = ["lane", "duo", "midjungle"];
  var LS_LANE = "lolcounter.lane";
  var LS_RECENT = "lolcounter.recent";

  var $ = function (id) { return document.getElementById(id); };
  var qEl = $("q"), suggestEl = $("suggest"), recentEl = $("recent"),
      lanesEl = $("lanes"), headEl = $("champhead"),
      tabsEl = $("tabs"), resEl = $("results"),
      verEl = $("ver"), srcEl = $("src"),
      dimsEl = $("dims"), secLane = $("sec-lane"),
      secDuo = $("sec-duo"), secMid = $("sec-midjungle"),
      duoMetaEl = $("duometa"), duoResEl = $("duoresults");

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* 英雄名：builds/duos 里只有 slug，用 champions.json 映射；映射不到显示 slug 本身 */
  function nameOf(slug) {
    return CHAMPS[slug] || { zh: slug, en: slug };
  }

  /* ---------- 状态 ---------- */
  var state = {
    slug: null,
    lane: "top",
    mode: "countered", // "countered" 克制它的 / "counters" 它克制的
    dim: "lane",       // "lane" 分路 Counter / "duo" 下路组合 / "midjungle" 中野组合
    duoBack: false,    // duo tab 里点过「← 回全榜」
    recent: []
  };
  try {
    var savedLane = localStorage.getItem(LS_LANE);
    if (savedLane && LANES.some(function (l) { return l[0] === savedLane; })) {
      state.lane = savedLane;
    }
    state.recent = JSON.parse(localStorage.getItem(LS_RECENT) || "[]");
    if (!Array.isArray(state.recent)) state.recent = [];
    state.recent = state.recent.filter(function (s) { return CHAMPS[s]; }).slice(0, 8);
  } catch (e) { /* localStorage 不可用时降级 */ }

  function saveRecent() {
    try { localStorage.setItem(LS_RECENT, JSON.stringify(state.recent)); } catch (e) {}
  }

  /* ---------- 时间格式化（北京时间） ---------- */
  function fmtBJ(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return iso || "未知";
    try {
      var p = new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit",
        day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false
      }).formatToParts(d).reduce(function (o, x) { o[x.type] = x.value; return o; }, {});
      return p.year + "-" + p.month + "-" + p.day + " " + p.hour + ":" + p.minute;
    } catch (e) {
      return iso;
    }
  }

  verEl.textContent = "数据版本 " + (META.patch || window.__CHAMPIONS__.patch || "未知") +
    " · 更新于 " + fmtBJ(META.scraped_at || window.__CHAMPIONS__.scraped_at) + "（北京时间）";
  srcEl.textContent = "数据来源：" + (META.source || "—") +
    " · " + (META.tier === "all" ? "全段位" : (META.tier || "—"));

  /* ---------- 维度 tab（切换时保持已选英雄与位置状态） ---------- */
  function setDim(dim) {
    state.dim = dim;
    Array.prototype.forEach.call(dimsEl.querySelectorAll("button"), function (b) {
      b.classList.toggle("active", b.dataset.dim === dim);
    });
    secLane.hidden = dim !== "lane";
    secDuo.hidden = dim !== "duo";
    secMid.hidden = dim !== "midjungle";
    srcEl.style.display = dim === "lane" ? "" : "none"; // duo tab 有自己的来源标注
    if (dim === "lane") { renderHead(); renderResults(); }
    if (dim === "duo") { renderDuo(); }
  }
  Array.prototype.forEach.call(dimsEl.querySelectorAll("button"), function (b) {
    b.addEventListener("click", function () { setDim(b.dataset.dim); });
  });

  /* ---------- 位置切换 ---------- */
  LANES.forEach(function (l) {
    var b = document.createElement("button");
    b.type = "button";
    b.textContent = l[1];
    b.dataset.lane = l[0];
    if (l[0] === state.lane) b.classList.add("active");
    b.addEventListener("click", function () {
      state.lane = l[0];
      try { localStorage.setItem(LS_LANE, l[0]); } catch (e) {}
      Array.prototype.forEach.call(lanesEl.children, function (x) {
        x.classList.toggle("active", x.dataset.lane === l[0]);
      });
      renderHead();
      renderResults();
    });
    lanesEl.appendChild(b);
  });

  /* ---------- 搜索联想 ---------- */
  function norm(s) { return s.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5]/g, ''); }
  function candidates(query) {
    var raw = query.trim(), q = norm(raw);
    if (!q) return [];
    var out = [];
    for (var slug in CHAMPS) {
      if (!Object.prototype.hasOwnProperty.call(CHAMPS, slug)) continue;
      var c = CHAMPS[slug];
      if (norm(c.zh).indexOf(q) >= 0 || norm(c.en).indexOf(q) >= 0 ||
          (c.alias && norm(c.alias).indexOf(q) >= 0)) {
        out.push(slug);
        if (out.length >= 8) break;
      }
    }
    return out;
  }

  function renderSuggest() {
    var list = candidates(qEl.value);
    suggestEl.innerHTML = "";
    if (!qEl.value.trim()) { suggestEl.hidden = true; return; }
    if (!list.length) {
      var li = document.createElement("li");
      li.className = "nohit";
      li.textContent = "搜不到，换个关键词";
      suggestEl.appendChild(li);
    } else {
      list.forEach(function (slug) {
        var c = CHAMPS[slug];
        var li = document.createElement("li");
        li.innerHTML = esc(c.zh) + '<span class="en">' + esc(c.en) + "</span>";
        li.addEventListener("click", function () { select(slug); });
        suggestEl.appendChild(li);
      });
    }
    suggestEl.hidden = false;
  }

  qEl.addEventListener("input", renderSuggest);
  qEl.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      var list = candidates(qEl.value);
      if (list.length) select(list[0]);
    }
  });
  document.addEventListener("click", function (e) {
    if (!suggestEl.hidden && !e.target.closest(".searchbox")) suggestEl.hidden = true;
  });
  qEl.addEventListener("focus", renderSuggest);

  /* ---------- 最近搜索 ---------- */
  function renderRecent() {
    recentEl.innerHTML = "";
    if (!state.recent.length || qEl.value.trim()) return;
    var t = document.createElement("span");
    t.className = "rtitle";
    t.textContent = "最近搜索";
    recentEl.appendChild(t);
    state.recent.forEach(function (slug) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.textContent = CHAMPS[slug].zh;
      b.addEventListener("click", function () { select(slug); });
      recentEl.appendChild(b);
    });
  }
  qEl.addEventListener("input", renderRecent);

  /* ---------- 选中英雄 ---------- */
  function select(slug) {
    state.slug = slug;
    state.duoBack = false; // 换英雄后 duo tab 回到默认视图
    state.recent = [slug].concat(state.recent.filter(function (s) { return s !== slug; })).slice(0, 8);
    saveRecent();
    suggestEl.hidden = true;
    renderRecent();
    renderHead();
    renderResults();
    if (state.dim === "duo") renderDuo();
  }

  /* ---------- 出装/符文数据 ---------- */
  function buildOf(slug, lane) {
    var b = BUILDS[slug];
    return b ? b[lane] : null;
  }

  function renderHead() {
    if (!state.slug) { headEl.innerHTML = ""; return; }
    var c = nameOf(state.slug);
    var html = '<span class="zh">' + esc(c.zh) + '</span><span class="en">' + esc(c.en) + "</span>";
    var b = buildOf(state.slug, state.lane);
    if (b) {
      html += '<div class="buildsum">出装 ' + esc(b.items.join(" / ")) +
        " · 符文 " + esc(b.keystone) +
        " · 胜率 " + Number(b.wr).toFixed(1) + "%</div>";
    }
    headEl.innerHTML = html;
  }

  function buildLineHTML(slug, lane) {
    var b = buildOf(slug, lane);
    if (!b) return "";
    return '<div class="buildline">出装 ' + esc(b.items.join("/")) +
      " · 基石 " + esc(b.keystone) +
      " · 胜率 " + Number(b.wr).toFixed(1) + "%</div>";
  }

  /* ---------- 颜色带（按对手胜率） ---------- */
  function band(opp) {
    if (opp >= 57) return ["red", "硬counter"];
    if (opp >= 54) return ["orange", null];
    if (opp >= 52) return ["amber", null];
    if (opp >= 50) return ["gray", null];
    return ["green", null];
  }

  /* ---------- 分路 tab ---------- */
  Array.prototype.forEach.call(tabsEl.querySelectorAll("button"), function (b) {
    b.addEventListener("click", function () {
      state.mode = b.dataset.mode;
      Array.prototype.forEach.call(tabsEl.children, function (x) {
        x.classList.toggle("active", x === b);
      });
      renderResults();
    });
  });

  /* ---------- 分路结果渲染 ---------- */
  function renderResults() {
    if (!state.slug) {
      resEl.innerHTML = '<div class="starthint">在上方搜索英雄，开始查询对位数据</div>';
      return;
    }
    var champData = DATA[state.slug] || {};
    var rows = champData[state.lane] || [];
    if (!rows.length) {
      resEl.innerHTML = '<div class="nodata">该位置暂无数据</div>';
      return;
    }
    rows = rows.slice();
    if (state.mode === "countered") {
      rows.sort(function (a, b) { return a[1] - b[1]; }); // wr 升序：被克制最惨在前
    } else {
      rows.sort(function (a, b) { return b[1] - a[1]; }); // wr 降序：它克制谁在前
    }
    var html = "";
    rows.forEach(function (r) {
      var slug = r[0], wr = r[1], games = r[2];
      var opp = 100 - wr; // 对手胜率
      var b = band(opp);
      var name = nameOf(slug);
      html += '<div class="row band-' + b[0] + '">' +
        '<div class="rowtop">' +
        '<div class="rname">' + esc(name.zh) + '<span class="en">' + esc(name.en) + "</span></div>" +
        '<div class="rstats">' +
          '<span class="oppwr ' + b[0] + '">' + opp.toFixed(1) + "%</span>" +
          (b[1] ? '<span class="badge">' + b[1] + "</span>" : "") +
          '<div class="games">' + games + " 局</div>" +
        "</div></div>" +
        buildLineHTML(slug, state.lane) +
        "</div>";
    });
    resEl.innerHTML = html;
  }

  /* ---------- 下路组合 ---------- */
  function duoRowHTML(slug, wr, games) {
    var c = nameOf(slug);
    return '<div class="duorow">' +
      '<div class="dname">' + esc(c.zh) + '<span class="en">' + esc(c.en) + "</span></div>" +
      '<div class="rstats"><span class="oppwr">' + Number(wr).toFixed(1) + "%</span>" +
      '<div class="games">' + games + " 局</div></div></div>";
  }

  function duoListHTML(rows, asc) {
    rows = (rows || []).slice();
    rows.sort(asc
      ? function (a, b) { return a[1] - b[1]; }
      : function (a, b) { return b[1] - a[1]; });
    if (!rows.length) return '<div class="nodata">暂无数据</div>';
    var html = "";
    rows.forEach(function (r) { html += duoRowHTML(r[0], r[1], r[2]); });
    return html;
  }

  function duoPairHTML(rows) {
    rows = (rows || []).slice();
    rows.sort(function (a, b) { return b[2] - a[2]; }); // 胜率降序
    if (!rows.length) return '<div class="nodata">暂无数据</div>';
    var html = "";
    rows.forEach(function (r) {
      var a = nameOf(r[0]), b = nameOf(r[1]);
      html += '<div class="duorow">' +
        '<div class="dname">' + esc(a.zh) + " + " + esc(b.zh) +
        '<span class="en">' + esc(a.en) + " + " + esc(b.en) + "</span></div>" +
        '<div class="rstats"><span class="oppwr">' + Number(r[2]).toFixed(1) + "%</span>" +
        '<div class="games">' + r[3] + " 局</div></div></div>";
    });
    return html;
  }

  function renderDuo() {
    if (!DUOS || !DUOS.meta) {
      duoMetaEl.textContent = "";
      duoResEl.innerHTML = '<div class="nodata">组合数据缺失</div>';
      return;
    }
    var m = DUOS.meta;
    duoMetaEl.textContent = "数据来源：" + (m.source || "—") +
      " · 版本 " + (m.patch || "—") +
      (m.patch_note ? " · " + m.patch_note : "");

    var bc = DUOS.by_champion || {};
    var html = "";
    if (state.slug && !state.duoBack && bc[state.slug]) {
      var c = nameOf(state.slug);
      html += '<button type="button" class="duoback" data-act="back">← 回全榜</button>';
      html += '<div class="duotitle">和 ' + esc(c.zh) + " 搭档胜率最高</div>";
      html += duoListHTML(bc[state.slug].best, false);
      html += '<details class="duoworst"><summary>最差搭档</summary>' +
        duoListHTML(bc[state.slug].worst, true) + "</details>";
    } else {
      if (state.slug && !bc[state.slug]) {
        html += '<div class="nodata">' + esc(nameOf(state.slug).zh) + " 暂无组合数据</div>";
      }
      html += '<div class="duotitle">下路组合全榜</div>';
      html += duoPairHTML(DUOS.ranking);
    }
    duoResEl.innerHTML = html;
  }

  duoResEl.addEventListener("click", function (e) {
    var t = e.target && e.target.closest ? e.target.closest('[data-act="back"]') : null;
    if (t) { state.duoBack = true; renderDuo(); }
  });

  /* ---------- 初始化 ---------- */
  renderRecent();
  if (state.recent.length) {
    select(state.recent[0]); // 打开即恢复上次看的英雄
  } else {
    renderResults();
  }
})();
