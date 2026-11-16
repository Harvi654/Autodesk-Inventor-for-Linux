# shellcheck shell=bash
# Step 0007: registry values of Autodesk's packages that hold the text
# %PUBLIC%\... as a plain string (REG_SZ), e.g. Inventor's Task Scheduler
# (TaskScheduler\Installation Path: DBQ, LogFile) and the API help
# (HTML Help: admapi_31_0.chm). Four ADIX packages map the folder token
# [{Common Documents}] to %PUBLIC%\Documents\, which install-from-image.py
# did not know before 2026-11-16, so it wrote the text unexpanded; a plain
# string is never expanded, so the path does not work. ODIS writes the
# real folder; this step does the same: %PUBLIC%\ -> C:\users\Public\.
# Only plain strings under Software\Autodesk and Software\Microsoft\Windows\
# HTML Help - Wine's own %PUBLIC% values are REG_EXPAND_SZ (str(2)) and stay.
# docs/installer-completeness-review.md, "Dry run with the finished branch".
MIG_DESC="registry: %PUBLIC%\\ in Autodesk's plain string values -> C:\\users\\Public\\"

# HIVE<TAB>KEY<TAB>NAME<TAB>NEW DATA for every value to fix (NAME "" = default)
_mig_public_values() {
    local f hive
    for hive in HKLM HKCU; do
        f="$WINEPREFIX/system.reg"; [ "$hive" = HKCU ] && f="$WINEPREFIX/user.reg"
        [ -f "$f" ] || continue
        python3 -I - "$f" "$hive" <<'PY'
import re, sys
path, hive = sys.argv[1], sys.argv[2]
unesc = lambda s: re.sub(r"\\(.)", r"\1", s)
key = None
for line in open(path, encoding="utf-8", errors="replace"):
    line = line.rstrip("\n")
    if line.startswith("["):
        k = unesc(line[1:line.rfind("]")])
        low = k.lower()
        key = k if (low.startswith("software\\autodesk\\")
                    or low == "software\\microsoft\\windows\\html help") else None
        continue
    if key is None:
        continue
    m = re.match(r'^(@|"((?:[^"\\]|\\.)*)")="((?:[^"\\]|\\.)*)"$', line)   # plain REG_SZ only
    if not m:
        continue
    data = unesc(m.group(3))
    if "%public%\\" not in data.lower():
        continue
    new = re.sub(r"(?i)%PUBLIC%\\", lambda _: "C:\\users\\Public\\", data)
    name = "" if m.group(1) == "@" else unesc(m.group(2))
    print("\t".join((hive, key, name, new)))
PY
    done
}

mig_needed() { [ -n "$(_mig_public_values)" ]; }

mig_apply() {
    local hive key name new n=0 list
    list="$(_mig_public_values)"
    wine_stop
    while IFS=$'\t' read -r hive key name new; do
        [ -n "$key" ] || continue
        if [ -n "$name" ]; then
            wine_reg_add "$hive\\$key" /v "$name" /t REG_SZ /d "$new"
        else
            wine_reg_add "$hive\\$key" /ve /t REG_SZ /d "$new"
        fi
        n=$((n + 1))
    done <<< "$list"
    wine_stop
    # read back (named values without spaces: what mig_reg_get can read)
    while IFS=$'\t' read -r hive key name new; do
        [ -n "$key" ] && [ -n "$name" ] && [[ "$name" != *[[:space:]]* ]] || continue
        [ "$(mig_reg_get "$hive\\$key" "$name")" = "$new" ] || { err "$hive\\$key -> $name did not change"; return 1; }
    done <<< "$list"
    info "    $n value(s) now point to C:\\users\\Public\\"
}
