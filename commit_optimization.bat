@echo off
cd /d C:\Users\fherr\Documents\FINAL\ANALISIS_COMPARATIVO
git add analisis\views\dashboard.py
git commit -m "feat: optimize dashboard queries from 7 to 3 using select_related and aggregate" ^
  -m "- Add Q operator import for conditional aggregation" ^
  -m "- Preload ForeignKey relationships with select_related on ResultadoTaxonomico" ^
  -m "- Preload VariedadClon relationship on MuestraSuelo" ^
  -m "- Consolidate 3 separate CatalogoMicroorganismo queries into 1 aggregate query" ^
  -m "  using Count with Q filters (benefico, fitopatogeno, sin_clasificar)" ^
  -m "- Add detailed comments explaining each optimization" ^
  -m "- Maintains exact same functionality and data accuracy" ^
  -m "- Reduces database round-trips by 57%%" ^
  -m "" ^
  -m "PHASE4-TASK1" ^
  -m "" ^
  -m "Co-authored-by: Copilot ^<223556219+Copilot@users.noreply.github.com^>"
echo.
echo Commit completed!
git log --oneline -1
pause
