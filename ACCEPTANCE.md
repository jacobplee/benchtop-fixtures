# Acceptance criteria

Written before any code. The build is done when every line below is checked off in `REPORT.md`
with the evidence that proves it. "Measured" means read back from the generated geometry
(B-rep faces, sections or the exported mesh), never restated from the construction code.

## A. Repository

- **A1** This file is the first commit in the history.
- **A2** `LICENSE` is MIT, `Copyright (c) 2026 Jacob Lee`. No email address or phone number
  appears in any tracked file.
- **A3** Generic bench hardware only. No reference to any specific research group, its
  instruments, its projects or its designs. Public standards and vendor-neutral specs are cited
  where their numbers are used.
- **A4** `README.md` has the overview render at the top, a part table with the parameters, how to
  generate and check a part, and design notes on the design-for-printing choices. No em dashes in
  any tracked text file.
- **A5** `.github/workflows/tests.yml` installs the pinned requirements and runs `pytest` on push
  and pull request. It parses as valid YAML.
- **A6** The repo has no remote. Nothing is pushed or published.
- **A7** Every commit message ends with the two attribution lines.

## B. Parts

Every part is a function of plain keyword parameters with working defaults, returns one valid
closed solid, is modeled in its print orientation (bed at z = 0) and declares its screw holes.

- **B1 Breadboard adapter plate.** `system="imperial"` gives 1/4-20 slots on a 25.4 mm grid,
  `system="metric"` gives M6 slots on a 25 mm grid. Counterbored clearance slots, one grid pitch of
  travel. A rectangular device bolt pattern on top with nut traps underneath.
  - Measured slot-end centres sit on the breadboard grid: every pairwise X and Y offset is an
    integer multiple of the pitch within 1e-6 mm, and slot travel equals one pitch.
  - Measured slot width equals the table clearance for the screw.
- **B2 Gridfinity-compatible bin.** N x M cells on the 42 mm pitch, height in 7 mm units, standard
  base profile, stacking lip, optional box or cylinder pocket cut into a solid fill.
  - Measured foot outline 35.6 mm at the bottom (r 0.8), 37.2 mm over the vertical band (r 1.6),
    41.5 mm at the top of the profile (r 3.75); profile heights 0.8 / 1.8 / 2.15 mm at 45 degrees.
  - Measured foot centres 42.000 mm apart; outer size 42 N - 0.5 by 42 M - 0.5 mm.
  - Body height 7 x units mm (base included, lip excluded); stacking lip 0.7 / 1.8 / 1.9 mm.
  - Stack test: a second bin set on top seats with zero interference at the height the profiles
    predict, and interferes if pushed 0.05 mm lower.
  - Source of every profile number cited in code and README.
- **B3 Syringe or tube cradle.** Built from a list of (barrel OD, barrel length). Each barrel gets
  two saddles with bore OD + clearance, placed at the minimum-sag support points
  (0.2232 L from each end). The layout follows the list (any length from 1 up).
- **B4 Cable and tube clip.** Bore OD + clearance. `style="snap"` gives a C-clip with a snap
  opening and a flat adhesive base; `style="screw"` adds a screw tab with a table clearance hole.
- **B5 Instrument foot or riser.** Round or square, tapered sides, anti-slip pad recesses on the
  bottom (count, diameter and depth as set), optional locating cup on top and optional centre
  screw with counterbore.

## C. Printability checker (`benchtop_fixtures/check.py`)

- **C1 Build volume.** Reports fit for Prusa MK4 (250 x 210 x 220), Bambu Lab X1C
  (256 x 256 x 256) and Formlabs Form 3 (145 x 145 x 185) in the modeled orientation, with a
  90 degree turn about Z allowed. Fails when a required printer does not fit.
- **C2 Minimum wall.** Local thickness sampled over the whole surface (inward rays from area-weighted
  surface samples, measured against the exact B-rep). Fails below the set minimum (default 1.2 mm).
  The method is documented.
- **C3 Screw holes.** Every declared hole is found in the B-rep and its measured diameter matches the
  table (M3, M4, M6, #8, 1/4-20; close and normal fit) within 0.01 mm. Table values cite their
  standard.
- **C4 Overhangs.** Every downward face steeper than 45 degrees from vertical that is not on the bed
  is reported. Flat ceilings no wider than the bridge limit (default 10 mm) are flagged as bridges
  and accepted; anything else is flagged as needing support and the verdict becomes FLAG. The
  approximation is documented.
- **C5** Every default part and every named preset gets verdict PASS.
- **C6** Deliberately bad parameters are caught: an oversize bin fails build volume, a thin clip wall
  fails minimum wall, a wrong device hole diameter fails the hole table, oversize riser pads and a
  too-narrow clip opening are flagged for overhangs. The checker also passes and fails known
  primitive shapes built inside the tests.
- **C7** Command line: `python -m benchtop_fixtures.check <part> [--set key=value ...]` prints the
  report and exits 0 for PASS, 1 for FAIL, 2 for FLAG.

## D. Outputs

- **D1** `exports/<name>.step` and `exports/<name>.stl` for every default part and preset. Every STL is
  watertight with consistent winding, and its volume matches the B-rep within 0.5 %.
- **D2** `exports/report.json` holds parameters, size, volume and the full check result for every export.
- **D3** `renders/<name>.png` per default part, same studio and camera direction for all, and
  `renders/overview.png` as a contact sheet.
- **D4** `pytest` passes locally. Tests cover volumes > 0, watertight solids, exact bolt-grid pitch,
  Gridfinity dimensions against the cited spec, and checker pass and fail cases.

## E. Hand-off

- **E1** `REPORT.md`: what is built, the pass or fail of every criterion above, the test count,
  the render paths, one suggested resume line, and the decisions left before going public.
