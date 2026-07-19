/**
 * Creates 80 CSS-animated snowflakes in #snow-container.
 * Motion is GPU-friendly (transform only); no rAF. Skipped when prefers-reduced-motion: reduce.
 */
(function () {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return;
  }

  var container = document.getElementById("snow-container");
  if (!container) {
    return;
  }

  function rand(min, max) {
    return min + Math.random() * (max - min);
  }

  var count = 80;
  var i;
  var size;
  var durFall;
  var swayAmt;
  var swayDur;
  var lane;
  var track;
  var flake;

  for (i = 0; i < count; i++) {
    size = rand(2, 6);
    /* Larger flakes fall slower (natural depth): 2px → ~8s, 6px → ~3s */
    durFall = 3 + ((6 - size) / 4) * 5;

    lane = document.createElement("div");
    lane.className = "snow-lane";
    lane.style.setProperty("--snow-x", rand(0, 100) + "%");

    track = document.createElement("div");
    track.className = "snowflake-track";
    track.style.setProperty("--fall-dur", durFall.toFixed(2) + "s");
    track.style.setProperty("--fall-delay", rand(0, 10).toFixed(2) + "s");

    flake = document.createElement("span");
    flake.className = "snowflake";
    flake.style.setProperty("--size", size.toFixed(2) + "px");
    flake.style.opacity = String(rand(0.3, 0.9).toFixed(2));

    swayAmt = rand(6, 16).toFixed(1) + "px";
    flake.style.setProperty("--sway-amt", swayAmt);
    swayDur = rand(2.2, 4.5).toFixed(2) + "s";
    flake.style.setProperty("--sway-dur", swayDur);
    flake.style.setProperty("--sway-delay", rand(0, 2.5).toFixed(2) + "s");

    /* Smaller = “farther” — subtle softening */
    if (size <= 3) {
      flake.style.filter = "blur(0.5px)";
    }

    track.appendChild(flake);
    lane.appendChild(track);
    container.appendChild(lane);
  }
})();
