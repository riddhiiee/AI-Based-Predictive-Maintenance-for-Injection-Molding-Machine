document.addEventListener(
  "DOMContentLoaded",
  () => {

    loadHistory();

    document
      .getElementById(
        "history-subsystem"
      )
      ?.addEventListener(
        "change",
        loadHistory
      );
  }
);


async function loadHistory() {

  const body =
    document.getElementById(
      "history-table-body"
    );

  const countEl =
    document.getElementById(
      "history-count"
    );

  if (!body) return;

  const subsystem =
    document.getElementById(
      "history-subsystem"
    )?.value || undefined;

  body.innerHTML = `
    <tr>
      <td colspan="6">
        <div class="loading-row">
          <span class="spinner"></span>
          Loading history…
        </div>
      </td>
    </tr>
  `;

  try {

    const data =
      await Api.getHistory(
        subsystem
          ? { subsystem }
          : {}
      );

    if (countEl) {

      countEl.textContent =
        `${data.count} cycle${
          data.count === 1
            ? ""
            : "s"
        }`;

    }

    if (!data.cycles.length) {

      body.innerHTML = `
        <tr>
          <td colspan="6">
            <div class="state-block">

              <h3>
                No live simulation history yet
              </h3>

              <p>
                Run the live simulation.
                Completed machine cycles
                will appear here automatically.
              </p>

            </div>
          </td>
        </tr>
      `;

      return;
    }

    body.innerHTML =
      data.cycles
        .map(renderCycle)
        .join("");

  } catch (err) {

    body.innerHTML = `
      <tr>
        <td colspan="6">
          ${Utils.errorBlock(err)}
        </td>
      </tr>
    `;
  }
}


function renderCycle(cycle) {

  const predictions =
    Array.isArray(cycle.predictions)
      ? cycle.predictions
      : Object.values(
          cycle.predictions || {}
        );

  const predictionHtml =
    predictions
      .map((p) => {

        const state =
          String(
            p.predicted_state ||
            "Healthy"
          );

        const status =
          state.toLowerCase();

        return `
          <span
            class="status-badge status-${status}"
            style="margin:2px;"
          >
            ${Utils.escapeHtml(
              p.subsystem_name || ""
            )}
            :
            ${Utils.escapeHtml(
              state
            )}
          </span>
        `;
      })
      .join("");

  const timestamp =
    cycle.generated_at ||
    cycle.timestamp ||
    "";

  return `
    <tr>

      <td>
        ${
          timestamp
            ? Utils.formatDate(timestamp)
            : "—"
        }

        <br>

        <span class="kpi-sub">
          ${
            timestamp
              ? Utils.formatTime(timestamp)
              : ""
          }
        </span>
      </td>

      <td class="cell-strong">
        ${Utils.escapeHtml(
          cycle.cycle_id || ""
        )}
      </td>

      <td>
        ${Utils.escapeHtml(
          cycle.mold || ""
        )}
      </td>

      <td>
        ${Utils.escapeHtml(
          cycle.material || ""
        )}
      </td>

      <td>
        <strong>
          ${cycle.overall_health ?? "—"}%
        </strong>
      </td>

      <td>
        ${predictionHtml}
      </td>

    </tr>
  `;
}