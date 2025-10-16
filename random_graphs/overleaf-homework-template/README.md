# Overleaf Homework Template (one `.tex` per homework)

This project uses the `subfiles` package so that **each homework lives in its own file** under `homework/` and can either be compiled on its own or included inside `main.tex`.

## How to use

1. Upload this whole folder (or the ZIP) to Overleaf.
2. Open `main.tex` and set:
   - `\coursename`, `\term`, `\authorname`.
3. Add your homeworks as separate files in `homework/` (e.g. `hw03.tex`) with:
   ```tex
   \documentclass[../main.tex]{subfiles}
   \begin{document}
   \section*{Homework 3}
   \addcontentsline{toc}{section}{Homework 3}
   \setcounter{section}{3} % so problems number as 3.x
   % ... your problems/solutions here ...
   \end{document}
   ```
4. In `main.tex`, include them with `\subfile{homework/hw03}` (no `.tex` extension).

### Compile individually
Open a homework file (e.g. `homework/hw01.tex`) in Overleaf and click “Recompile”. Thanks to `\documentclass[../main.tex]{subfiles}`, it inherits the preamble and compiles standalone.

### Customize
- Put global macros/theorem styles in `preamble/macros.tex`.
- Add packages in `main.tex` as needed.
