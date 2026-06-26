## Expanded Color System

### New Accent Tokens
- `--accent-rose-700`: `#9f1d59`
- `--accent-rose-500`: `#c63a77`
- `--accent-rose-100`: `#ffe1ec`
- `--accent-amber-700`: `#8a4b00`
- `--accent-amber-500`: `#b66a12`
- `--accent-amber-100`: `#fff0d1`
- `--accent-sky-700`: `#0f5f88`
- `--accent-sky-500`: `#1f88b5`
- `--accent-sky-100`: `#dff4ff`
- `--accent-mint-700`: `#0d7c67`
- `--accent-mint-500`: `#1ea789`
- `--accent-mint-100`: `#ddfbf3`
- `--accent-plum-700`: `#6d28d9`
- `--accent-plum-500`: `#8c52ef`
- `--accent-plum-100`: `#efe5ff`

### Updated Supporting Tokens
- `Primary`: expanded with `--primary-800`, `--primary-500`, and `--primary-200` for stronger depth and softer tinting.
- `Secondary`: expanded with `--secondary-800`, `--secondary-600`, and `--secondary-200` for utility actions and decorative layering.
- `Neutral`: expanded into a fuller scale from `--neutral-950` to `--neutral-050` for text, borders, backgrounds, and elevated surfaces.

### Usage Guidelines
- Use `primary` and `plum` blends for main actions, navigation emphasis, and high-priority call-to-action buttons.
- Use `sky` and `mint` accents for informative, clinical, and supportive states such as cards, form surfaces, and selection panels.
- Use `rose` for destructive or urgent emphasis and `amber` for warm highlights, pending states, and decorative balance.
- Use `neutral` tokens for text, background layers, and border structure to keep hierarchy stable while the palette becomes more vibrant.
- Use the `100` variants as tinted backgrounds and the `700` variants for readable foreground text or high-contrast icon treatment.

### Accessibility Audit
- `#4533d4` on `#ffffff`: `7.84:1`
- `#0f766e` on `#ffffff`: `5.47:1`
- `#9f1d59` on `#ffffff`: `7.52:1`
- `#8a4b00` on `#ffffff`: `6.80:1`
- `#0f5f88` on `#ffffff`: `6.97:1`
- `#6d28d9` on `#ffffff`: `7.10:1`
- `#10233d` on `#ffffff`: `15.79:1`
- `#43546d` on `#f7f9ff`: `7.31:1`
- `#0f7a48` on `#dcfce8`: `4.91:1`
- `#8a4b00` on `#fff1d6`: `6.09:1`
- `#b91c3d` on `#ffe2e7`: `5.24:1`
- `#1d4ed8` on `#dbeafe`: `5.49:1`

### Implementation Notes
- All shared color tokens are centralized in `static/css/style.css` so the palette can scale without hard-coded one-off colors.
- The protected “Design Principles” content in `templates/home.html` was left unchanged; the color expansion is implemented entirely through the styling system and supporting documentation.
- Cross-browser rendering should still be manually spot-checked in Chrome, Edge, Firefox, and Safari for final release approval.
