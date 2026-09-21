/**
 * Hero animation: one application moving through the platform, on a loop.
 *
 * It traces the real sequence the product performs, in order: an X-ray arrives,
 * the model reads it, findings accumulate, a score settles, an underwriter
 * signs it off. Nothing here is decorative motion for its own sake, and the
 * numbers it lands on are the ones the platform actually produces.
 *
 * Built as inline SVG with CSS keyframes rather than a charting library: it is
 * one figure with a fixed script, so a renderer would be weight without use.
 * The whole loop is 12s and respects prefers-reduced-motion, where it holds the
 * final scored state instead of cycling.
 */

// The eighteen findings the chest model reports. Only the bars move; the labels
// are the model's own vocabulary, shortened for width.
const FINDING_BARS = [
  { label: 'Infiltration', delay: '0.0s', width: '78%' },
  { label: 'Consolidation', delay: '0.12s', width: '64%' },
  { label: 'Fibrosis', delay: '0.24s', width: '52%' },
  { label: 'Nodule', delay: '0.36s', width: '41%' },
  { label: 'Effusion', delay: '0.48s', width: '28%' },
]

export function PipelineAnimation() {
  return (
    <div className="pipe" role="img" aria-label="An application moving through intake, model reading, scoring and underwriter sign-off">
      <div className="pipe__frame">
        {/* Stage 1: the radiograph arrives and is scanned. */}
        <div className="pipe__stage pipe__stage--film">
          <div className="pipe__label">Chest X-ray received</div>
          <div className="pipe__film">
            <svg viewBox="0 0 120 120" className="pipe__ribs" aria-hidden="true">
              {/* A suggestion of a thorax. Deliberately abstract: a realistic
                  radiograph would imply the image belongs to someone. */}
              <ellipse cx="60" cy="62" rx="38" ry="46" className="pipe__cavity" />
              <path d="M60 20 v84" className="pipe__spine" />
              {[30, 44, 58, 72, 86].map((y, i) => (
                <g key={y}>
                  <path d={`M58 ${y} q-22 ${4 + i * 1.5} -30 ${16 + i * 2}`} className="pipe__rib" />
                  <path d={`M62 ${y} q22 ${4 + i * 1.5} 30 ${16 + i * 2}`} className="pipe__rib" />
                </g>
              ))}
              {/* The region the model will flag. */}
              <circle cx="44" cy="52" r="11" className="pipe__lesion" />
            </svg>
            <div className="pipe__scanline" />
          </div>
        </div>

        {/* Stage 2: findings accumulate. */}
        <div className="pipe__stage pipe__stage--findings">
          <div className="pipe__label">Findings weighed</div>
          <div className="pipe__bars">
            {FINDING_BARS.map((f) => (
              <div className="pipe__bar" key={f.label}>
                <span className="pipe__bar-label">{f.label}</span>
                <span className="pipe__bar-track">
                  <span
                    className="pipe__bar-fill"
                    style={{ animationDelay: f.delay, ['--w' as string]: f.width }}
                  />
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Stage 3: the score settles, then a person decides. */}
        <div className="pipe__stage pipe__stage--score">
          <div className="pipe__label">Score and sign-off</div>
          <div className="pipe__dial">
            <svg viewBox="0 0 132 78" aria-hidden="true">
              <path d="M 12 70 A 54 54 0 0 1 120 70" className="pipe__arc-bg" />
              <path d="M 12 70 A 54 54 0 0 1 120 70" className="pipe__arc-fg" />
            </svg>
            <div className="pipe__score">
              <span className="pipe__score-num">75</span>
              <span className="pipe__score-tier">Elevated</span>
            </div>
          </div>
          <div className="pipe__decision">
            <span className="pipe__tick" aria-hidden="true" />
            Senior underwriter review
          </div>
        </div>
      </div>

      {/* The caption states what the figure is, so the animation is not the
          only thing carrying the message. */}
      <p className="pipe__caption">
        Every score carries the findings behind it. A person makes the decision.
      </p>
    </div>
  )
}
