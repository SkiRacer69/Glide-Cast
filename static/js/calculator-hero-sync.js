/**
 * Keeps the calculator hero (venue · discipline, schedule line, caption)
 * in sync with form fields, and re-syncs when the language changes.
 */
(function () {
  var venue = document.getElementById("id_venue");
  var discipline = document.getElementById("id_discipline");
  var raceDate = document.getElementById("id_race_date");
  var run1 = document.getElementById("id_run1_time");
  var run2 = document.getElementById("id_run2_time");
  var snowMode = document.getElementById("id_snow_mode");
  var dirty = document.getElementById("id_dirty_abrasive");

  var titleEl = document.getElementById("calc-hero-title");
  var scheduleEl = document.getElementById("calc-hero-schedule");
  var captionEl = document.getElementById("calc-hero-caption");

  if (!titleEl || !scheduleEl) return;

  function t(key) {
    return (window.I18N && window.I18N.t) ? window.I18N.t(key) : key;
  }

  function locale() {
    return (window.I18N && window.I18N.locale) ? window.I18N.locale() : "en-US";
  }

  function selectedLabel(selectEl) {
    if (!selectEl || selectEl.selectedIndex < 0) return "";
    return selectEl.options[selectEl.selectedIndex].text.trim();
  }

  function formatHeroDate(iso) {
    if (!iso) return "";
    var d = new Date(iso + "T12:00:00");
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(locale(), {
      weekday: "long", month: "short", day: "numeric", year: "numeric",
    });
  }

  function formatHeroTime(timeStr) {
    if (!timeStr) return "";
    var parts = String(timeStr).trim().split(":");
    var h = parseInt(parts[0], 10);
    var m = parseInt(parts[1], 10) || 0;
    if (isNaN(h)) return timeStr;
    var d = new Date();
    d.setHours(h, m, 0, 0);
    return d.toLocaleTimeString(locale(), { hour: "numeric", minute: "2-digit", hour12: true });
  }

  function sync() {
    var v = selectedLabel(venue);
    var disc = selectedLabel(discipline);
    titleEl.textContent = (v || "—") + " · " + (disc || "—");

    var datePart = raceDate && raceDate.value ? formatHeroDate(raceDate.value) : "";
    var r1 = run1 && run1.value ? formatHeroTime(run1.value) : "";
    var r2 = run2 && run2.value ? formatHeroTime(run2.value) : "";
    scheduleEl.textContent =
      (datePart || "—") + " · " + t("hero.run1") + " " + (r1 || "—") +
      " · " + t("hero.run2") + " " + (r2 || "—");

    if (captionEl) {
      var sm = snowMode ? selectedLabel(snowMode) : "";
      var base = (sm ? sm + t("hero.snow_connector") : "") + t("hero.caption");
      if (dirty && dirty.checked) base += t("hero.dirty_flag");
      captionEl.textContent = base;
    }
  }

  var watch = [venue, discipline, raceDate, run1, run2, snowMode, dirty];
  watch.forEach(function (el) {
    if (!el) return;
    el.addEventListener("change", sync);
    if (el.tagName === "SELECT") el.addEventListener("input", sync);
    if (el.type === "date" || el.type === "time") el.addEventListener("input", sync);
  });

  /* Re-sync when language changes so hero text updates immediately */
  document.addEventListener("glidecast:langchange", sync);

  sync();
})();
