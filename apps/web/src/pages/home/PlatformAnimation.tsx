/**
 * The hero: one client's files moving through the platform, on a 12 second
 * loop. Four documents arrive, each is read by its own reader, the readings
 * become one score, and a person records the decision. CSS only; every
 * element's delay is its cue in the loop, so the sequence stays in step.
 *
 * Deliberately generic. The documents are a scan, a trace, a lab sheet and a
 * note; no reader is named, because the point is the shape of the process,
 * and readers are added without the process changing.
 */
export function PlatformAnimation() {
  return (
    <div className="flow" aria-hidden="true">
      {/* Column 1: the client's files, arriving one by one. */}
      <div className="flow__col flow__col--files">
        <div className="flow__label">Client's files</div>
        <div className="flow__doc flow__doc--1">
          <svg viewBox="0 0 40 40">
            <rect x="6" y="6" width="28" height="28" rx="3" className="flow__doc-frame" />
            <ellipse cx="20" cy="21" rx="9" ry="11" className="flow__doc-scan" />
          </svg>
          <span>Scan</span>
        </div>
        <div className="flow__doc flow__doc--2">
          <svg viewBox="0 0 40 40">
            <rect x="6" y="6" width="28" height="28" rx="3" className="flow__doc-frame" />
            <path d="M8 22 h6 l3 -8 l4 14 l3 -9 l2 3 h6" className="flow__doc-trace" />
          </svg>
          <span>Trace</span>
        </div>
        <div className="flow__doc flow__doc--3">
          <svg viewBox="0 0 40 40">
            <rect x="6" y="6" width="28" height="28" rx="3" className="flow__doc-frame" />
            <path d="M11 14 h18 M11 20 h18 M11 26 h18 M20 12 v16" className="flow__doc-grid" />
          </svg>
          <span>Lab sheet</span>
        </div>
        <div className="flow__doc flow__doc--4">
          <svg viewBox="0 0 40 40">
            <rect x="6" y="6" width="28" height="28" rx="3" className="flow__doc-frame" />
            <path d="M11 14 h18 M11 19 h14 M11 24 h18 M11 29 h10" className="flow__doc-lines" />
          </svg>
          <span>Note</span>
        </div>
      </div>

      {/* The lines between columns light as files travel. */}
      <div className="flow__wires">
        <span className="flow__wire flow__wire--1" />
        <span className="flow__wire flow__wire--2" />
        <span className="flow__wire flow__wire--3" />
        <span className="flow__wire flow__wire--4" />
      </div>

      {/* Column 2: a reader for each kind of file. */}
      <div className="flow__col flow__col--readers">
        <div className="flow__label">Read by AI</div>
        <div className="flow__reader flow__reader--1">
          <span className="flow__reader-dot" />
          <span className="flow__reader-bar" />
        </div>
        <div className="flow__reader flow__reader--2">
          <span className="flow__reader-dot" />
          <span className="flow__reader-bar" />
        </div>
        <div className="flow__reader flow__reader--3">
          <span className="flow__reader-dot" />
          <span className="flow__reader-bar" />
        </div>
        <div className="flow__reader flow__reader--4">
          <span className="flow__reader-dot" />
          <span className="flow__reader-bar" />
        </div>
      </div>

      <div className="flow__wires flow__wires--join">
        <span className="flow__wire flow__wire--join" />
      </div>

      {/* Column 3: one score, one plan, one decision by a person. */}
      <div className="flow__col flow__col--result">
        <div className="flow__label">Decided by your team</div>
        <div className="flow__result">
          <div className="flow__dial">
            <svg viewBox="0 0 132 78">
              <path d="M 12 70 A 54 54 0 0 1 120 70" className="flow__arc-bg" />
              <path d="M 12 70 A 54 54 0 0 1 120 70" className="flow__arc-fg" />
            </svg>
            <div className="flow__score">
              <span className="flow__score-num">One score</span>
              <span className="flow__score-sub">from every reading</span>
            </div>
          </div>
          <div className="flow__plan">
            <span className="flow__plan-line flow__plan-line--1" />
            <span className="flow__plan-line flow__plan-line--2" />
          </div>
          <div className="flow__decision">
            <span className="flow__tick" />
            Recorded by an underwriter
          </div>
        </div>
      </div>
    </div>
  )
}
