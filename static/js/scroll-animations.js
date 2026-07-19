/**
 * glideCast — scroll animations via Intersection Observer.
 * Respects prefers-reduced-motion (disables all scroll-in animations).
 */
(function () {
  'use strict';

  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reducedMotion) {
    document.querySelectorAll(
      '.scroll-anim-card, .scroll-anim-chart, .scroll-anim-header, .scroll-anim-summary, .scroll-anim-slide-left, .scroll-anim-fade-right'
    ).forEach(function (el) {
      el.classList.add('is-visible');
    });
    return;
  }

  var observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      });
    },
    { rootMargin: '0px 0px -50px 0px', threshold: 0.05 }
  );

  function observeAll(selector) {
    document.querySelectorAll(selector).forEach(function (el) {
      observer.observe(el);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      observeAll('.scroll-anim-card');
      observeAll('.scroll-anim-chart');
      observeAll('.scroll-anim-header');
      observeAll('.scroll-anim-summary');
      observeAll('.scroll-anim-slide-left');
      observeAll('.scroll-anim-fade-right');
    });
  } else {
    observeAll('.scroll-anim-card');
    observeAll('.scroll-anim-chart');
    observeAll('.scroll-anim-header');
    observeAll('.scroll-anim-summary');
    observeAll('.scroll-anim-slide-left');
    observeAll('.scroll-anim-fade-right');
  }
})();
