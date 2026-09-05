/**
 * Machine schematic hotspot interactions.
 *
 * Behaviour:
 * - Hover -> show tooltip temporarily
 * - Move mouse from marker into tooltip -> keep tooltip open
 * - Click marker -> pin tooltip
 * - Click "View prediction" -> works normally
 * - Click elsewhere -> close tooltip
 * - Escape -> close pinned tooltip
 */

document.addEventListener("DOMContentLoaded", () => {
  const wrap = document.getElementById("schematic-wrap");
  const tooltip = document.getElementById("schematic-tooltip");

  if (!wrap || !tooltip) return;

  const zoneMap = {
    heater: document.getElementById("schematic-heater-bands"),
    clamp: document.getElementById("schematic-clamp-mold"),
    hydraulic: document.getElementById("schematic-hydraulic-cyl"),
  };

  let subsystemData = {};
  let hideTimer = null;
  let pinnedHotspot = null;
  let tooltipHovered = false;

  Api.getSubsystems()
    .then((data) => {
      data.subsystems.forEach((s) => {
        subsystemData[s.id] = s;

        const statusClass = `status-${s.status}`;

        wrap
          .querySelectorAll(`.hotspot[data-subsystem="${s.id}"]`)
          .forEach((el) => {
            el.classList.remove(
              "status-unknown",
              "status-healthy",
              "status-warning",
              "status-critical",
              "status-degrading"
            );

            el.classList.add(statusClass);
          });

        if (zoneMap[s.id]) {
          zoneMap[s.id].classList.remove(
            "status-unknown",
            "status-healthy",
            "status-warning",
            "status-critical",
            "status-degrading"
          );

          zoneMap[s.id].classList.add(statusClass);
        }
      });
    })
    .catch((err) =>
      Utils.toast(
        err.message || "Could not load machine status.",
        "error"
      )
    );

  wrap.querySelectorAll(".hotspot").forEach((hotspot) => {

    hotspot.addEventListener("mouseenter", () => {
      clearHideTimer();

      if (!pinnedHotspot) {
        showTooltip(hotspot);
      }
    });

    hotspot.addEventListener("focus", () => {
      clearHideTimer();

      if (!pinnedHotspot) {
        showTooltip(hotspot);
      }
    });

    hotspot.addEventListener("mouseleave", () => {
      if (!pinnedHotspot) {
        scheduleHide();
      }
    });

    hotspot.addEventListener("blur", () => {
      if (!pinnedHotspot) {
        scheduleHide();
      }
    });

    hotspot.addEventListener("click", (event) => {
      event.stopPropagation();

      clearHideTimer();

      if (pinnedHotspot === hotspot) {
        pinnedHotspot = null;
        tooltip.hidden = true;
        return;
      }

      pinnedHotspot = hotspot;
      showTooltip(hotspot);
    });
  });

  /**
   * Important:
   * keep the tooltip visible while the cursor is over it.
   */
  tooltip.addEventListener("mouseenter", () => {
    tooltipHovered = true;
    clearHideTimer();
  });

  tooltip.addEventListener("mouseleave", () => {
    tooltipHovered = false;

    if (!pinnedHotspot) {
      scheduleHide();
    }
  });

  tooltip.addEventListener("click", (event) => {
    event.stopPropagation();
  });

  /**
   * Clicking outside closes a pinned tooltip.
   */
  document.addEventListener("click", (event) => {
    if (
      !tooltip.hidden &&
      !tooltip.contains(event.target) &&
      !event.target.closest(".hotspot")
    ) {
      pinnedHotspot = null;
      tooltip.hidden = true;
    }
  });

  /**
   * Escape also closes the tooltip.
   */
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      pinnedHotspot = null;
      tooltip.hidden = true;
    }
  });

  function clearHideTimer() {
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
  }

  function scheduleHide() {
    clearHideTimer();

    hideTimer = setTimeout(() => {
      if (!pinnedHotspot && !tooltipHovered) {
        tooltip.hidden = true;
      }
    }, 350);
  }

  function showTooltip(hotspot) {
    const id = hotspot.getAttribute("data-subsystem");
    const data = subsystemData[id];

    if (!data) return;

    clearHideTimer();

    tooltip.innerHTML = `
      <h4>${Utils.escapeHtml(data.name)}</h4>

      <span class="status-badge status-${data.status}">
        ${Utils.escapeHtml(Utils.capitalize(data.status))}
      </span>

      <p>
        Confidence ${(data.confidence * 100).toFixed(0)}%
        ·
        ${Utils.escapeHtml(data.diagnostic_text)}
      </p>

      <a href="/predictions?subsystem=${encodeURIComponent(id)}">
        View prediction →
      </a>
    `;

    tooltip.hidden = false;

    const wrapRect = wrap.getBoundingClientRect();
    const dot =
      hotspot.querySelector(".hotspot-dot") ||
      hotspot;

    const dotRect = dot.getBoundingClientRect();

    const tooltipWidth =
      tooltip.offsetWidth || 240;

    const tooltipHeight =
      tooltip.offsetHeight || 130;

    let left =
      dotRect.left -
      wrapRect.left +
      dotRect.width +
      12;

    let top =
      dotRect.top -
      wrapRect.top -
      15;

    if (left + tooltipWidth > wrapRect.width - 8) {
      left =
        dotRect.left -
        wrapRect.left -
        tooltipWidth -
        12;
    }

    if (left < 8) {
      left = 8;
    }

    if (top + tooltipHeight > wrapRect.height - 8) {
      top =
        wrapRect.height -
        tooltipHeight -
        8;
    }

    if (top < 8) {
      top = 8;
    }

    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  }
});