---
name: maldi-polymer-ms
description: Domain reference for MALDI-TOF polymer spectra — raw spectrum import, baseline/smoothing/peak picking, repeat-unit periodicity and series detection, Kendrick mass defect, isotope handling, and scoring composition candidates by consecutive repeat counts. Use when implementing or reviewing spectrum processing, series filtering, or composition-likelihood code in MPCS.
---

# MALDI polymer MS — algorithms and pitfalls

## 1. Raw spectrum files
- Typical exports: 2 columns (m/z, intensity), separated by tab, comma, semicolon, or spaces. May have no header, `#`/`##` comment lines, a trailing blank line, or a European decimal comma (`1234,56;789`). Bruker flexAnalysis/mMass/OpenChrom `.txt`/`.xy`/`.csv` are all variants of this.
- Detect format: skip lines that do not start with a number; split on `[\t,; ]+` unless a decimal comma is detected; take the first two numeric columns. Require monotonically increasing m/z (sort if not).
- Size: 10^4–10^6 points. Keep as `numpy` arrays and never loop in Python over raw points.

## 2. Pre-processing → peak list
1. **Baseline**: SNIP or a rolling-minimum + smoothing filter; window ≈ 5–10× peak width.
2. **Smoothing**: Savitzky–Golay (`scipy.signal.savgol_filter`), window of an odd number of points ≈ FWHM.
3. **Noise**: robust σ = 1.4826·MAD of the baseline-subtracted signal (or local MAD per m/z window, because noise varies with m/z).
4. **Peak picking**: `scipy.signal.find_peaks(y, prominence=k·σ, distance=…)` with S/N threshold k≈3–5.
5. **Centroid**: intensity-weighted centroid over the top ~50 % of the peak, or a 3-point parabolic fit. Report centroid m/z, height, area, S/N.
6. **Isotopes**: above ~3–5 kDa with linear-mode TOF, isotopes are unresolved, so use **average mass** (`mass_type="AVERAGE"`). If resolved (reflectron, < ~5 kDa), group the isotope cluster (Δ = 1.00335/z) and keep either the monoisotopic peak (`isotope_offset=0`) or the most-abundant peak plus a known offset.

## 3. Periodicity (homologous series)
A polymer series is a set of peaks separated by the repeat-unit mass M_r (e.g. EO 44.0262, LA 72.0211, St 104.0626, MMA 100.0524).
- **Known M_r** (from the monomer table): build a graph on picked peaks with an edge i→j when |(m_j − m_i) − k·M_r| ≤ tol for k=1 (allow k=2,3 as gaps with a penalty). Connected chains of length ≥ L_min (≈4–5) are series. Different end groups/adducts give *parallel* series with the same spacing.
- **Unknown M_r**: histogram all pairwise Δm of the top-N peaks (Δ < ~500 Da, bin ≈ tol). The dominant bins are repeat units or their combinations. Alternatively, autocorrelate the binned spectrum.
- **Kendrick mass defect (KMD)**: `KM = m · round(M_r)/M_r`, `KMD = round(KM) − KM` (or `nominal − KM`). Members of one series share KMD (a horizontal line), and different end-group/adduct families sit on different lines. This is the standard visual filter for copolymers: plot KMD vs m/z, and the user selects a band to select a series. For low resolution use the fractional-base / remainder-of-KM variant (`m mod M_r`) instead.
- **Copolymers** (A_x B_y): peaks form a 2-D lattice. Series along A and along B both exist. Detect each spacing separately and use 2-D KMD (base A, then base B).

## 4. Composition likelihood from series consistency
Within one series spaced by monomer A, the true assignments of consecutive peaks differ by exactly +1 A, with every other count, the end group, the adduct, and the isotope offset unchanged.
- **Family key**: for each candidate on each peak, key = (composition with A removed, adduct, end group, isotope_offset). Group candidates by key across the series' peaks.
- **Family score** (log-likelihood style):
  - mass term: Σ_peaks −(err/σ)²/2 with σ ≈ tol/2 (or σ from a calibration fit)
  - coverage: number of series peaks explained / series length (a family that explains 1 peak is noise)
  - contiguity: the A counts must be strictly consecutive along the ordered peaks, with a penalty per gap
  - optional priors: isotope_offset 0 preferred; fewer "exotic" units; feed ratio closeness
- **Posterior-like probability**: softmax of family scores across competing families of the same series, then per-peak probability = Σ over families containing that candidate. This fills `SolverResult.probability`, which already exists and currently shows "-".
- When families conflict (overlapping series), solve as a Viterbi/DP over ordered peaks: states are candidates, transition reward if Δcomposition = +e_A, plus emission from the mass error.
- **Requirement**: the per-peak solver must keep *all* candidates within tolerance (or a high cap), not the top 100, or the true family may be truncated away.
- **Systematic error**: real spectra often have a constant or linear m/z offset. Fit `err = a + b·m` over the best family and report it. A consistent offset is evidence for that family, and a random scatter is evidence against it.

## 5. Validation data
Build synthetic spectra in tests: pick a true family (e.g. `EO_n LA_5 HDI_1 + Na`, n=20..60 with a Poisson/Schulz–Zimm intensity distribution), generate isotope envelopes (molmass, see `_compute_isotope_peaks` in `mpcs/gui/dialogs/isotope_pattern_dialog.py`, which should be moved to `mpcs/core/`), convolve with a Gaussian peak shape, add baseline + noise, then assert the pipeline recovers the series and ranks the true family first.
