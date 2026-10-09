document.addEventListener("DOMContentLoaded", () => {
  if (!window.gsap || !window.ScrollTrigger) return;
  gsap.registerPlugin(ScrollTrigger);

  const mm = gsap.matchMedia();
  mm.add({ motion: "(prefers-reduced-motion: no-preference)", desktop: "(min-width: 701px)" }, ({ conditions }) => {
    if (!conditions.motion) return;

    const cover = document.querySelector(".cover");
    const entrance = gsap.timeline({ defaults: { ease: "power3.out" } });
    entrance.from(".site-header", { autoAlpha: .7, y: -8, duration: .5 })
      .from(".kicker", { autoAlpha: 0, y: 14, duration: .5 }, "<.1")
      .from(".hero h1", { autoAlpha: .3, y: 27, duration: .9 }, "<.12")
      .from(".hero-description, .hero-actions", { autoAlpha: 0, y: 18, duration: .65, stagger: .1 }, "<.2")
      .from(".cover", { autoAlpha: .5, y: 26, rotation: 1.5, duration: 1 }, "<.12")
      .from(".hero-index", { autoAlpha: 0, y: 10, duration: .5 }, "<.2");

    gsap.to(".scroll-progress", { scaleX: 1, ease: "none", scrollTrigger: { trigger: document.documentElement, start: 0, end: "max", scrub: .25 } });
    gsap.from(".about-grid > *", { autoAlpha: 0, y: 24, duration: .72, stagger: .11, ease: "power2.out", scrollTrigger: { trigger: ".about", start: "top 78%", once: true } });
    gsap.from(".notes-heading", { autoAlpha: 0, y: 22, duration: .7, ease: "power2.out", scrollTrigger: { trigger: ".notes", start: "top 82%", once: true } });
    gsap.from(".article-card", { autoAlpha: 0, y: 32, duration: .8, ease: "power2.out", scrollTrigger: { trigger: ".article-card", start: "top 85%", once: true } });
    gsap.from(".visual-steps div", { autoAlpha: 0, x: 15, duration: .55, stagger: .14, ease: "power2.out", scrollTrigger: { trigger: ".article-visual", start: "top 80%", once: true } });

    const coverMotion = [
      gsap.to(".orbit-inner", { rotation: 360, duration: 42, ease: "none", repeat: -1, paused: true }),
      gsap.to(".cover-monogram", { y: -6, duration: 4, ease: "sine.inOut", repeat: -1, yoyo: true, paused: true })
    ];
    const syncCover = () => {
      const rect = cover.getBoundingClientRect();
      const visible = !document.hidden && rect.bottom > 0 && rect.top < innerHeight;
      coverMotion.forEach(animation => visible ? animation.resume() : animation.pause());
    };
    ScrollTrigger.create({ trigger: cover, start: "top bottom", end: "bottom top", onToggle: syncCover });
    document.addEventListener("visibilitychange", syncCover);
    syncCover();

    let move;
    let reset;
    if (conditions.desktop) {
      const xTo = gsap.quickTo(".cover-art", "x", { duration: .8, ease: "power2.out" });
      const yTo = gsap.quickTo(".cover-art", "y", { duration: .8, ease: "power2.out" });
      move = event => {
        const rect = cover.getBoundingClientRect();
        xTo(((event.clientX - rect.left) / rect.width - .5) * 12);
        yTo(((event.clientY - rect.top) / rect.height - .5) * 12);
      };
      reset = () => { xTo(0); yTo(0); };
      cover.addEventListener("pointermove", move);
      cover.addEventListener("pointerleave", reset);
    }

    return () => {
      document.removeEventListener("visibilitychange", syncCover);
      if (move) { cover.removeEventListener("pointermove", move); cover.removeEventListener("pointerleave", reset); }
      coverMotion.forEach(animation => animation.kill());
    };
  });
});
