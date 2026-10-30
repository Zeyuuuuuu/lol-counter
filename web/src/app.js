/* LOL counter 速查 — 纯静态，无外部请求 */
(function () {
  "use strict";

  var CHAMPS = (window.__CHAMPIONS__ && window.__CHAMPIONS__.champions) || {};
  var META = window.__COUNTERS__ ? window.__COUNTERS__.meta : {};
  var DATA = window.__COUNTERS__ ? window.__COUNTERS__.data : {};
  var BUILDS = window.__BUILDS__ ? window.__BUILDS__.data : {};
  var DUOS = window.__DUOS__ || null;
  var MAYHEM = window.__MAYHEM__ || null;
  var AUGN = window.__AUGMENT_NAMES__ || {};

  var LANES = [
    ["top", "上"], ["jungle", "野"], ["middle", "中"],
    ["bottom", "下"], ["support", "辅"]
  ];
  var REGIONS = [
    ["world", "全球"], ["kr", "韩服"], ["na1", "北美"], ["euw1", "欧西"]
  ];
  var DIMS = ["lane", "duo", "mayhem"];
  var LS_LANE = "lolcounter.lane";
  var LS_RECENT = "lolcounter.recent";
  var LS_REGION = "lolcounter.region";

  var $ = function (id) { return document.getElementById(id); };
  var qEl = $("q"), suggestEl = $("suggest"), recentEl = $("recent"),
      lanesEl = $("lanes"), headEl = $("champhead"),
      tabsEl = $("tabs"), resEl = $("results"),
      verEl = $("ver"), srcEl = $("src"),
      dimsEl = $("dims"), secLane = $("sec-lane"),
      secDuo = $("sec-duo"), secMayhem = $("sec-mayhem"),
      duoMetaEl = $("duometa"), duoResEl = $("duoresults"),
      duoRegionEl = $("duoregionhint"),
      mayhemRegionEl = $("mayhemregion"), mayhemMetaEl = $("mayhemmeta"),
      mayhemHeroEl = $("mayhemhero"), mayhemBackEl = $("mayhemback"),
      mayhemBackBtn = $("mayhembackbtn"),
      mayhemTitleEl = $("mayhemtitle"), mayhemResEl = $("mayhemresults"),
      regionEl = $("region"), laneRegionHintEl = $("laneregionhint");

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
    region: "world",
    mode: "countered", // "countered" 克制它的 / "counters" 它克制的
    dim: "lane",       // "lane" 分路 Counter / "duo" 下路组合 / "mayhem" 海克斯大乱斗
    duoBack: false,    // duo tab 里点过「← 回全榜」
    mayhemBack: false, // mayhem tab 里点过「← 回全榜」
    mayhemScrollY: 0,  // 进 mayhem 英雄详情前榜单的滚动位置（返回时恢复）
    mayhemTier: "all", // mayhem 详情页强化等级筛选：all/prismatic/gold/silver
    recent: []
  };
  try {
    var savedLane = localStorage.getItem(LS_LANE);
    if (savedLane && LANES.some(function (l) { return l[0] === savedLane; })) {
      state.lane = savedLane;
    }
    var savedRegion = localStorage.getItem(LS_REGION);
    if (savedRegion && REGIONS.some(function (r) { return r[0] === savedRegion; })) {
      state.region = savedRegion;
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
  srcEl.textContent = "数据来源：" + (META.source || "—") + " · 全球" +
    " · " + (META.tier === "all" ? "全段位" : (META.tier || "—"));

  function regionName(r) {
    for (var i = 0; i < REGIONS.length; i++) {
      if (REGIONS[i][0] === r) return REGIONS[i][1];
    }
    return r;
  }

  /* ---------- 维度 tab（切换时保持已选英雄与位置状态） ---------- */
  function setDim(dim) {
    state.dim = dim;
    Array.prototype.forEach.call(dimsEl.querySelectorAll("button"), function (b) {
      b.classList.toggle("active", b.dataset.dim === dim);
    });
    secLane.hidden = dim !== "lane";
    secDuo.hidden = dim !== "duo";
    secMayhem.hidden = dim !== "mayhem";
    srcEl.style.display = dim === "lane" ? "" : "none"; // duo/mayhem tab 有自己的来源标注
    if (dim === "lane") { renderHead(); renderResults(); }
    if (dim === "duo") { renderDuo(); }
    if (dim === "mayhem") { renderMayhem(); }
  }
  Array.prototype.forEach.call(dimsEl.querySelectorAll("button"), function (b) {
    b.addEventListener("click", function () { setDim(b.dataset.dim); });
  });

  /* ---------- 地区筛选 ---------- */
  regionEl.value = state.region;
  function renderRegionHint() {
    // 对位与海克斯大乱斗数据都只有全球统计；下路组合跟随地区切换
    if (state.region === "world") {
      laneRegionHintEl.hidden = true;
      laneRegionHintEl.textContent = "";
    } else {
      laneRegionHintEl.hidden = false;
      laneRegionHintEl.textContent =
        "对位与海克斯大乱斗数据暂无分区统计，当前显示全球数据";
    }
  }
  regionEl.addEventListener("change", function () {
    state.region = regionEl.value;
    try { localStorage.setItem(LS_REGION, state.region); } catch (e) {}
    renderRegionHint();
    if (state.dim === "duo") renderDuo();
    if (state.dim === "mayhem") renderMayhem();
  });
  renderRegionHint();

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
      var hit = norm(c.zh).indexOf(q) >= 0 || norm(c.en).indexOf(q) >= 0 ||
          (c.alias && norm(c.alias).indexOf(q) >= 0) ||
          (c.nicks && c.nicks.some(function (n) { return norm(n).indexOf(q) >= 0; }));
      if (hit) {
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
    if (state.dim === "mayhem") {
      // 记住榜单滚动位置，点「← 回全榜」时恢复
      try {
        state.mayhemScrollY = window.scrollY ||
          (document.documentElement && document.documentElement.scrollTop) || 0;
      } catch (e) { state.mayhemScrollY = 0; }
    }
    state.slug = slug;
    state.duoBack = false; // 换英雄后 duo tab 回到默认视图
    state.mayhemBack = false; // 换英雄后 mayhem tab 进入详情视图
    state.mayhemTier = "all"; // 换英雄后强化等级筛选回到全部
    state.recent = [slug].concat(state.recent.filter(function (s) { return s !== slug; })).slice(0, 8);
    saveRecent();
    suggestEl.hidden = true;
    renderRecent();
    renderHead();
    renderResults();
    if (state.dim === "duo") renderDuo();
    if (state.dim === "mayhem") renderMayhem();
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
    return '<div class="duorow" data-slug="' + slug + '">' +
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
      html += '<div class="duorow" data-slug="' + r[0] + '">' +
        '<div class="dname">' + esc(a.zh) + " + " + esc(b.zh) +
        '<span class="en">' + esc(a.en) + " + " + esc(b.en) + "</span></div>" +
        '<div class="rstats"><span class="oppwr">' + Number(r[2]).toFixed(1) + "%</span>" +
        '<div class="games">' + r[3] + " 局</div></div></div>";
    });
    return html;
  }

  function duoData() {
    if (!DUOS || !DUOS.regions) return null;
    return DUOS.regions[state.region] || DUOS.regions.world || null;
  }

  function renderDuo() {
    var dd = duoData();
    var m = (DUOS && DUOS.meta) || {};
    if (!dd) {
      duoMetaEl.textContent = "";
      duoRegionEl.hidden = true;
      duoRegionEl.textContent = "";
      duoResEl.innerHTML = '<div class="nodata">组合数据缺失</div>';
      return;
    }
    duoMetaEl.textContent = "数据来源：data.nerfplz.com · 下路组合 · Silver+ 多地区混合 · " +
      "版本 " + (m.patch || "—");
    if (state.region === "world") {
      duoRegionEl.hidden = true;
      duoRegionEl.textContent = "";
    } else {
      duoRegionEl.hidden = false;
      duoRegionEl.textContent = "下路组合暂无分区数据，当前显示 Silver+ 多地区混合数据";
    }

    var bc = dd.by_champion || {};
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
        html += '<div class="nodata">暂无组合数据</div>';
      }
      html += '<div class="duotitle">下路组合全榜</div>';
      html += duoPairHTML(dd.ranking);
    }
    duoResEl.innerHTML = html;
  }

  duoResEl.addEventListener("click", function (e) {
    if (!e.target || !e.target.closest) return;
    var back = e.target.closest('[data-act="back"]');
    if (back) { state.duoBack = true; renderDuo(); return; }
    // 榜单行点击：全榜点组合行选中 ADC 看它的搭档；英雄视图点搭档行看该搭档的组合
    var row = e.target.closest('.duorow[data-slug]');
    if (row && row.dataset.slug && CHAMPS[row.dataset.slug]) select(row.dataset.slug);
  });

  /* ---------- 海克斯大乱斗 ---------- */
  // 强化名三语：英文原名 / 国服简体 / 台服繁体（缺译名时只显示英文）
  function augName3(en) {
    var t = AUGN[en];
    var parts = [en];
    if (t) {
      if (t.cn && t.cn !== en) parts.push(t.cn);
      if (t.tw && t.tw !== en && t.tw !== t.cn) parts.push(t.tw);
    }
    return parts.join(" / ");
  }

  function mayhemRows() {
    return (MAYHEM && MAYHEM.ranking) || [];
  }

  function renderMayhem() {
    var rows = mayhemRows();
    var m = (MAYHEM && MAYHEM.meta) || {};
    mayhemMetaEl.textContent = "数据来源：mayhemmeta.com · 海克斯大乱斗 · 全球数据" +
      " · 版本 " + (m.patch_display || m.patch || "—");
    if (state.region === "world") {
      mayhemRegionEl.hidden = true;
      mayhemRegionEl.textContent = "";
    } else {
      mayhemRegionEl.hidden = false;
      mayhemRegionEl.textContent = "海克斯大乱斗暂无分区数据，当前显示全球数据";
    }
    var bc = (MAYHEM && MAYHEM.by_champion) || {};
    if (!rows.length) {
      mayhemBackEl.hidden = true;
      mayhemHeroEl.hidden = true;
      mayhemHeroEl.innerHTML = "";
      mayhemResEl.innerHTML = '<div class="nodata">海克斯大乱斗数据缺失</div>';
      return;
    }
    var selIdx = -1;
    if (state.slug) {
      for (var i = 0; i < rows.length; i++) {
        if (rows[i][0] === state.slug) { selIdx = i; break; }
      }
    }
    // 选中英雄且未点回全榜：详情独占整页；否则显示总榜
    var showDetail = selIdx >= 0 && !state.mayhemBack;
    mayhemBackEl.hidden = !showDetail;
    if (showDetail) {
      var info = bc[state.slug] || {};
      var c = nameOf(state.slug);
      var allAugs = info.top_augments || [];
      /* 强化等级：AUGN[name].tier（prismatic/gold/silver），缺失时为空 */
      function augTier(a) {
        var t = AUGN[a.name];
        return (t && t.tier) || "";
      }
      var tierName = { all: "全部", prismatic: "棱彩", gold: "金色", silver: "银色" };
      var tierTag = { prismatic: "棱", gold: "金", silver: "银" };
      var counts = { all: allAugs.length, prismatic: 0, gold: 0, silver: 0 };
      allAugs.forEach(function (a) {
        var tr = augTier(a);
        if (counts[tr] !== undefined) counts[tr]++;
      });
      var curTier = state.mayhemTier || "all";
      var list = allAugs.filter(function (a) {
        return curTier === "all" || augTier(a) === curTier;
      });
      var augHtml = "";
      list.forEach(function (a) {
        var d = a.diff;
        var dTxt = (d > 0 ? "+" : "") + d.toFixed(2);
        var dCls = d > 0 ? "up" : (d < 0 ? "down" : "");
        var tr = augTier(a);
        augHtml += '<div class="augrow">' +
          (tr ? '<span class="augtier ' + tr + '">' + tierTag[tr] + "</span>" : "") +
          '<div class="augname">' + esc(augName3(a.name)) + "</div>" +
          '<div class="augstats"><span class="oppwr">' + a.win.toFixed(2) + "%</span>" +
          '<span class="agames">' + a.pick.toFixed(2) + "% 登场</span>" +
          '<span class="adiff ' + dCls + '">' + dTxt + "</span></div></div>";
      });
      var filterHtml = '<div class="augfilter">' +
        ["all", "prismatic", "gold", "silver"].map(function (k) {
          return '<button type="button" data-tier="' + k + '"' +
            (k === curTier ? ' class="active"' : "") + ">" +
            tierName[k] + " " + counts[k] + "</button>";
        }).join("") + "</div>";
      mayhemHeroEl.hidden = false;
      mayhemHeroEl.innerHTML =
        '<div class="aname">' + esc(c.zh) + '<span class="en">' + esc(c.en) + "</span></div>" +
        '<div class="astats">' +
        '<div><b>' + Number(info.winrate).toFixed(2) + "%</b><span>胜率</span></div>" +
        '<div><b>#' + info.rank + "</b><span>排名</span></div>" +
        '<div><b>' + info.games + "</b><span>对局数</span></div>" +
        '<div><b>' + Number(info.pickrate).toFixed(2) + "%</b><span>登场率</span></div>" +
        "</div>" +
        filterHtml +
        (augHtml ? '<div class="augtitle">海克斯强化胜率（' + list.length + " 个" +
                   (curTier !== "all" ? " · " + tierName[curTier] : "") +
                   ' · 对局数≥100 · 按胜率排序）</div>' +
                   '<div class="auglist">' + augHtml + "</div>"
                 : '<div class="nodata">该等级暂无强化数据</div>');
      mayhemTitleEl.hidden = true;
      mayhemResEl.hidden = true;
      try { window.scrollTo(0, 0); } catch (e) {}
      return;
    }
    mayhemHeroEl.hidden = true;
    mayhemHeroEl.innerHTML = "";
    mayhemTitleEl.hidden = false;
    mayhemResEl.hidden = false;
    mayhemTitleEl.textContent = "海克斯大乱斗胜率榜 · 全球";
    var html = "";
    rows.forEach(function (r, i) {
      var name = nameOf(r[0]);
      html += '<div class="aramrow' + (i === selIdx ? " hl" : "") + '"' +
        ' data-slug="' + r[0] + '"' +
        (i === selIdx ? ' id="mayhemsel"' : "") + ">" +
        '<div class="arank">' + (i + 1) + "</div>" +
        '<div class="dname">' + esc(name.zh) + '<span class="en">' + esc(name.en) + "</span></div>" +
        '<div class="rstats"><span class="oppwr">' + Number(r[1]).toFixed(2) + "%</span>" +
        '<div class="games">' + r[3] + " 局 · " + Number(r[2]).toFixed(2) +
        "% 登场</div></div></div>";
    });
    mayhemResEl.innerHTML = html;
    if (selIdx >= 0) {
      var sel = $("mayhemsel");
      if (sel && sel.scrollIntoView) {
        try { sel.scrollIntoView({ block: "center" }); } catch (e) {}
      }
    }
  }

  /* 海克斯大乱斗榜单行点击 = 选中该英雄（与搜索选中效果完全一致） */
  mayhemResEl.addEventListener("click", function (e) {
    var t = e.target && e.target.closest ? e.target.closest('.aramrow[data-slug]') : null;
    if (t && t.dataset.slug && CHAMPS[t.dataset.slug]) select(t.dataset.slug);
  });

  /* 海克斯大乱斗「← 回全榜」：回到总榜，恢复进入详情前的滚动位置；地区选择不重置 */
  mayhemBackBtn.addEventListener("click", function () {
    state.mayhemBack = true;
    renderMayhem();
    try { window.scrollTo(0, state.mayhemScrollY || 0); } catch (e) {}
  });

  /* 海克斯大乱斗详情页强化等级筛选：全部/棱彩/金色/银色 */
  mayhemHeroEl.addEventListener("click", function (e) {
    var b = e.target && e.target.closest ?
      e.target.closest('.augfilter button[data-tier]') : null;
    if (b && b.dataset.tier) {
      state.mayhemTier = b.dataset.tier;
      renderMayhem();
    }
  });

  /* ---------- 初始化 ---------- */
  renderRecent();
  if (state.recent.length) {
    select(state.recent[0]); // 打开即恢复上次看的英雄
  } else {
    renderResults();
  }
})();
