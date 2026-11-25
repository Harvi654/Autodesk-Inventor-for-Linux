#!/usr/bin/env python3
"""Capture focused Inventor/Nastran metadata locally. Never commit captures.

Vendor files are streamed only to compute hashes. Fusion logs are generated
diagnostics. Neither the capture nor the comparison sends data anywhere.
"""
import argparse
from collections import defaultdict
import hashlib
import html
import os
from pathlib import Path
import re
import socket
import sys


CLASSES = r"software\classes"
AUTODESK = r"software\autodesk"
DOTNET = r"software\microsoft\.netframework"
FUSION = r"software\microsoft\fusion"
ENVIRONMENT = r"system\currentcontrolset\control\session manager\environment"
COMPUTER_NAME = r"system\currentcontrolset\control\computername"
DOTNET_ROOTS = (DOTNET, DOTNET.replace("microsoft", r"wow6432node\microsoft"))
FUSION_ROOTS = (FUSION, FUSION.replace("microsoft", r"wow6432node\microsoft"))
SHELL_FOLDERS = r"software\microsoft\windows\currentversion\explorer\shell folders"
METADATA = {
    ("HKCU", "volatile environment"): {"userprofile", "username", "computername"},
    ("HKCU", SHELL_FOLDERS): {"appdata"},
    ("HKLM", COMPUTER_NAME + r"\computername"): {"computername"},
    ("HKLM", COMPUTER_NAME + r"\activecomputername"): {"computername"},
}
PATH_KEYS = {("HKCU", "environment"), ("HKLM", ENVIRONMENT)}
COM_FAMILIES = {"clsid", "typelib", "interface", "appid"}
CLASS_RESERVED = {"applications", "directory", "drive", "folder", "installer", "mime",
                  "packagedcom", "systemfileassociations", "wow6432node"}
PRODUCT = re.compile(r"nastran|nei|newpf|neprogress", re.I)
GAC_PRODUCT = re.compile(r"nastran|nei|newpf", re.I)
PROTECTED = re.compile(r"adsklicensing|licenses|idsdk|identity", re.I)
SECRET = re.compile(r"serial|licen|token|password|secret|key$", re.I)
SID = re.compile(r"\bS-\d+(?:-\d+){2,}\b", re.I)
FUSION_FIELD = re.compile(
    r"^(?:LOG:\s*)?(Calling assembly|DisplayName|Bind result)\s*[:=]\s*(.*)$", re.I
)
PHASES = ("before", "installed", "started")
FILE_ROOTS = (
    "ProgramData/Autodesk/Inventor 2027/Addins",
    "Program Files/Autodesk/Inventor Nastran 2027",
)
GAC_ROOTS = ("Windows/assembly/GAC_MSIL", "Windows/Microsoft.NET/assembly/GAC_MSIL")
REG_TYPES = {
    0: "REG_NONE", 1: "REG_SZ", 2: "REG_EXPAND_SZ", 3: "REG_BINARY",
    4: "REG_DWORD", 5: "REG_DWORD_BIG_ENDIAN", 6: "REG_LINK",
    7: "REG_MULTI_SZ", 8: "REG_RESOURCE_LIST", 9: "REG_FULL_RESOURCE_DESCRIPTOR",
    10: "REG_RESOURCE_REQUIREMENTS_LIST", 11: "REG_QWORD",
}
KEY = re.compile(r"^\[((?:\\.|[^\\\]])*)\](?:\s+\d+)?$")
ESCAPE = re.compile(r'\\(?:x([0-9a-fA-F]{1,4})|([0-7]{1,3})|(.))')
VALUE = re.compile(r'^(?:"((?:\\.|[^"\\])*)"|(@))\s*=\s*(.*)$')


def field(text):
    return re.sub(r"[%|\x00-\x1f\x7f]",
                  lambda match: f"%{ord(match[0]):02X}", text)


def list_field(items):
    return " ; ".join(field(item).replace(";", "%3B") for item in items)


def ordinal(text):
    return text.encode("utf-16-be", errors="surrogatepass")


class Mask:
    def __init__(self, users=(), profiles=(), machines=()):
        self.rules = []
        for profile in sorted(set(profiles), key=lambda item: (-len(item), item)):
            if profile:
                parts = re.split(r"[\\/]+", profile.rstrip("\\/"))
                expr = r"[\\/]+".join(re.escape(part) for part in parts)
                self.rules.append((re.compile(r"(?<![\w])" + expr + r"(?=$|[\\/\s\"'|;,>])",
                                              re.I), "<profile>"))
        names = {name: "<user>" for name in users if name}
        names.update({name: "<machine>" for name in machines if name})
        for name, replacement in sorted(names.items(), key=lambda pair: (-len(pair[0]), pair[0])):
            self.rules.append((re.compile(r"(?<![\w<])" + re.escape(name) +
                                          r"(?![\w>])", re.I), replacement))

    def __call__(self, value):
        value = SID.sub("<sid>", value)
        for pattern, replacement in self.rules:
            value = pattern.sub(replacement, value)
        return value

    def binary(self, data):
        for encoding in ("utf-8", "utf-16-le", "utf-16-be"):
            decoded = data.decode(encoding, errors="replace")
            if self(decoded) != decoded or PROTECTED.search(decoded):
                return "<masked>"
        return data.hex()


def unescape(text):
    escapes = {"n": "\n", "r": "\r", "t": "\t", "a": "\a", "b": "\b",
               "f": "\f", "v": "\v"}
    escapes["e"] = "\x1b"
    def decode(match):
        if match[1]:
            return chr(int(match[1], 16))
        if match[2]:
            return chr(int(match[2], 8))
        return escapes.get(match[3], match[3])
    value = ESCAPE.sub(decode, text)
    # Wine can encode a supplementary character as two UTF-16 escapes.
    return value.encode("utf-16-le", errors="surrogatepass").decode("utf-16-le", errors="replace")


def under(path, root):
    return path == root or path.startswith(root + "\\")


def relevant_scope(hive, path):
    if PROTECTED.search(path):
        return False
    if under(path, CLASSES):
        return com_group(path) is not None
    if under(path, AUTODESK):
        tail = path[len(AUTODESK):]
        return "nastran" in tail or (
            hive == "HKCU" and under(path, AUTODESK + r"\inventor\registryversion31.0")
            and "addins" in path.split("\\")[4:]
        )
    if (hive, path) in PATH_KEYS or (hive, path) in METADATA:
        return True
    return hive == "HKLM" and (
        any(path == root or under(path, root + r"\policy\v4.0") for root in DOTNET_ROOTS)
        or any(under(path, root) for root in FUSION_ROOTS)
    )


def registry_string(kind, value):
    if kind == 7:
        text = value.rstrip("\0")
        value = text.split("\0") if text else []
    return REG_TYPES.get(kind, f"REG_{kind}"), value


def parse_value(raw):
    if raw.startswith('"') and raw.endswith('"'):
        return "REG_SZ", unescape(raw[1:-1])
    quoted = re.fullmatch(r'str\(([0-9a-fA-F]+)\):"(.*)"', raw)
    if quoted:
        kind = int(quoted[1], 16)
        return registry_string(kind, unescape(quoted[2]))
    if raw.startswith("dword:"):
        return "REG_DWORD", int(raw[6:], 16)
    data_match = re.fullmatch(r"hex(?:\(([0-9a-fA-F]+)\))?:(.*)", raw)
    if not data_match:
        raise ValueError("unsupported Wine registry value syntax")
    kind = int(data_match[1], 16) if data_match[1] else 3
    data = bytes.fromhex(data_match[2].replace(",", " "))
    if kind in {1, 2, 6, 7}:
        value = data.decode("utf-16-le").rstrip("\0")
        return registry_string(kind, value)
    if kind in (4, 5, 11):
        return REG_TYPES[kind], int.from_bytes(data, "big" if kind == 5 else "little")
    return REG_TYPES.get(kind, f"REG_{kind}"), data


def registry_lines(path):
    with path.open(encoding="utf-8-sig") as source:
        pending = ""
        first = 0
        for number, line in enumerate(source, 1):
            if not pending:
                first = number
            pending += line.strip()
            if pending.endswith("\\"):
                pending = pending[:-1]
            else:
                yield first, pending
                pending = ""
        if pending:
            raise ValueError(f"{path.name}:{first}: incomplete registry value")


def current_control_set(path):
    """Find the physical target of Wine's HKLM System\\CurrentControlSet alias."""
    scope = None
    selected = None
    for _, line in registry_lines(path):
        if line.startswith("["):
            match = KEY.fullmatch(line)
            scope = unescape(match[1]).lower() if match else None
        elif scope == r"system\currentcontrolset":
            if re.fullmatch(r'"SymbolicLinkValue"\s*=\s*hex\(6\):.*', line, re.I):
                try:
                    _, target = parse_value(VALUE.fullmatch(line)[3])
                except (ValueError, UnicodeError):
                    continue
                physical = re.fullmatch(r"\\registry\\machine\\(system\\controlset\d{3,})",
                                        target, re.I)
                if physical:
                    return physical[1].lower()
        elif scope == r"system\select":
            match = re.fullmatch(r'"Current"\s*=\s*dword:([0-9a-f]+)', line, re.I)
            if match and int(match[1], 16):
                selected = f"system\\controlset{int(match[1], 16):03d}"
    return selected


def load_registry(path, hive):
    tree = {}
    values = None
    control_set = current_control_set(path) if hive == "HKLM" else None
    for number, line in registry_lines(path):
        if line.startswith("["):
            values = None
            match = KEY.fullmatch(line)
            if not match:
                continue
            key = unescape(match[1]).lower()
            if control_set and under(key, control_set):
                key = r"system\currentcontrolset" + key[len(control_set):]
            if relevant_scope(hive, key):
                values = tree.setdefault(key, {})
                # Wine can omit a section for an implicit parent of a saved key.
                ancestor = key.rpartition("\\")[0]
                while ancestor and relevant_scope(hive, ancestor):
                    tree.setdefault(ancestor, {})
                    ancestor = ancestor.rpartition("\\")[0]
        elif values is not None and (match := VALUE.fullmatch(line)):
            name = unescape(match[1]).lower() if match[1] else ""
            allowed = {"path"} if (hive, key) in PATH_KEYS else METADATA.get((hive, key))
            if allowed is not None and name not in allowed:
                continue
            if SECRET.search(name):
                # Only identify the type. Secret data also cannot select a COM subtree.
                raw = match[3]
                kind = re.match(r"(?:str|hex)\(([0-9a-fA-F]+)\):", raw)
                if kind:
                    code = int(kind[1], 16)
                    tag = REG_TYPES.get(code, f"REG_{code}")
                elif raw.startswith("dword:"):
                    tag = "REG_DWORD"
                else:
                    tag = "REG_BINARY" if raw.startswith("hex:") else "REG_SZ"
                values[name] = tag, "<masked>"
                continue
            try:
                values[name] = parse_value(match[3])
            except (ValueError, UnicodeError) as exc:
                raise ValueError(f"{path.name}:{number}: invalid or unsupported registry data") from exc
    return tree


def com_group(path):
    if not path.startswith(CLASSES + "\\"):
        return None
    parts = path[len(CLASSES) + 1:].split("\\")
    if parts[0] == "wow6432node":
        base = CLASSES + "\\wow6432node"
        parts = parts[1:]
    else:
        base = CLASSES
    if not parts or parts[0].startswith(".") or parts[0] in CLASS_RESERVED:
        return None
    if parts[0] in COM_FAMILIES:
        return base + "\\" + "\\".join(parts[:2]) if len(parts) >= 2 else None
    return base + "\\" + parts[0]


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        yield from value


def inventors_server(value):
    path = value.lower().replace("/", "\\").strip('" ')
    return path.rsplit("\\", 1)[-1] == "mscoree.dll" or bool(
        re.search(r"(?:^|\\)inventor(?: nastran)? 2027\\", path)
    )


def selected_com(tree):
    selected = set()
    for key, values in tree.items():
        group = com_group(key)
        if not group or group in selected:
            continue
        category, leaf = group.split("\\")[-2:]
        if (category not in COM_FAMILIES and "." not in leaf and not PRODUCT.search(leaf)
                and group + r"\clsid" not in tree and group + r"\curver" not in tree):
            continue
        inproc = category == "clsid" and key == group + r"\inprocserver32"
        if PRODUCT.search(key) or any(
            PRODUCT.search(name) or any(
                not PROTECTED.search(text) and (
                    PRODUCT.search(text) or (inproc and name == "" and inventors_server(text))
                ) for text in strings(value)
            ) for name, (_, value) in values.items()
        ):
            selected.add(group)
    return selected


def rendered(kind, name, value, mask, is_path):
    if SECRET.search(name):
        return "<masked>"
    if isinstance(value, bytes):
        return mask.binary(value)
    if is_path and isinstance(value, str):
        return list_field(mask(item.strip()) if not PROTECTED.search(item) else "<masked>"
                          for item in value.split(";"))
    if isinstance(value, list):
        return list_field(mask(item) if not PROTECTED.search(item) else "<masked>" for item in value)
    if isinstance(value, str) and PROTECTED.search(value):
        return "<masked>"
    return field(mask(str(value)))


def registry_rows(hive, tree, mask):
    groups = selected_com(tree)
    for key, values in tree.items():
        if under(key, CLASSES) and com_group(key) not in groups:
            continue
        if (hive, key) in METADATA:
            continue
        is_env = (hive, key) in PATH_KEYS
        if is_env and "path" not in values:
            continue
        prefix = f"REG {hive}\\{field(mask(key))}"
        if not values:
            yield f"{prefix} |  | KEY | "
        for name, (kind, value) in values.items():
            yield f"{prefix} | {field(mask(name))} | {kind} | {rendered(kind, name, value, mask, is_env)}"


def real_child(path, name):
    if path.is_symlink() or not path.is_dir():
        return None
    matches = [item for item in path.iterdir() if item.name.lower() == name.lower()]
    if len(matches) > 1:
        raise ValueError("ambiguous case-insensitive Windows path in prefix")
    return matches[0] if matches and not matches[0].is_symlink() else None


def drive_path(drive, relative):
    current = drive
    for name in re.split(r"[\\/]", relative):
        if not name or name in (".", ".."):
            return None
        current = real_child(current, name)
        if current is None:
            return None
    return current


def children(path):
    if path is None or path.is_symlink() or not path.is_dir():
        return
    for child in path.iterdir():
        if not child.is_symlink() and not PROTECTED.search(child.name):
            yield child


def file_entries(root, directories=False):
    for child in children(root):
        if child.is_dir():
            if directories:
                yield child
            yield from file_entries(child, directories)
        elif child.is_file():
            yield child


def digest(path):
    sha = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(chunk)
            size += len(chunk)
    return size, sha.hexdigest()


def item_value(tree, key, name):
    value = tree.get(key, {}).get(name, (None, ""))[1]
    return value if isinstance(value, str) else ""


def fusion_rows(drive, mask):
    root = drive_path(drive, "fusionlog")
    for path in file_entries(root):
        if path.suffix.lower() != ".htm":
            continue
        name = field(mask(path.relative_to(root).as_posix().lower()))
        yield f"FUSION {name} | file | "
        with path.open("rb") as raw:
            bom = raw.read(4)
        encoding = "utf-16" if bom.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        with path.open(encoding=encoding, errors="replace") as source:
            for line in source:
                plain = html.unescape(re.sub(r"<[^>]*>", "", line)).strip()
                match = FUSION_FIELD.match(plain)
                if match:
                    value = match[2].strip()
                    safe = "<masked>" if PROTECTED.search(value) else field(mask(value))
                    yield f"FUSION {name} | {match[1].lower()} | {safe}"


def capture(prefix, include_fusion=False):
    drive = prefix / "drive_c"
    if drive.is_symlink() or not drive.is_dir():
        raise ValueError("the prefix needs a real drive_c directory")
    machine = load_registry(prefix / "system.reg", "HKLM")
    user = load_registry(prefix / "user.reg", "HKCU")
    users_root = drive_path(drive, "users")
    profiles = [path for path in children(users_root) if path.is_dir()
                and path.name.lower() not in ("public", "default", "default user", "all users")]
    profile_paths = ["C:\\Users\\" + path.name for path in profiles]
    profile = item_value(user, "volatile environment", "userprofile")
    appdata = item_value(user, SHELL_FOLDERS, "appdata")
    conventional = re.match(r"^([a-z]:[\\/]users[\\/]([^\\/]+))(?=[\\/]|$)", appdata, re.I)
    usernames = [path.name for path in profiles]
    usernames.append(item_value(user, "volatile environment", "username"))
    if conventional:
        profile_paths.append(conventional[1])
        usernames.append(conventional[2])
    if profile:
        profile_paths.append(profile)
    profile_paths.extend(path[3:] for path in tuple(profile_paths) if re.match(r"^[a-z]:[\\/]", path, re.I))
    machines = [socket.gethostname(), item_value(user, "volatile environment", "computername")]
    machines.extend(item_value(machine, key, "computername")
                    for hive, key in METADATA if hive == "HKLM")
    mask = Mask(usernames, profile_paths, machines)
    yield from registry_rows("HKLM", machine, mask)
    yield from registry_rows("HKCU", user, mask)
    roots = [drive_path(drive, name) for name in FILE_ROOTS]
    if re.match(r"^c:[\\/]", appdata, re.I):
        roots.append(drive_path(drive, appdata[3:] + r"\Autodesk\Inventor 2027\Addins"))
    else:
        app_roots = [root for path in profiles if
                     (root := drive_path(path, "AppData/Roaming/Autodesk/Inventor 2027/Addins"))]
        if len(app_roots) > 1:
            raise ValueError("multiple Addins profiles and no Wine AppData registry mapping")
        roots.extend(app_roots)
    for root in roots:
        for path in file_entries(root):
            rel = path.relative_to(drive).as_posix().lower()
            if not PROTECTED.search(rel):
                size, sha = digest(path)
                yield f"FILE {field(mask(rel))} | {size} | {sha}"
    for name in GAC_ROOTS:
        for assembly in children(drive_path(drive, name)):
            if not GAC_PRODUCT.search(assembly.name):
                continue
            yield f"FILE {field(mask(assembly.relative_to(drive).as_posix().lower()))} | - | -"
            for path in file_entries(assembly, directories=True):
                yield f"FILE {field(mask(path.relative_to(drive).as_posix().lower()))} | - | -"
    if include_fusion:
        yield from fusion_rows(drive, mask)


def read_capture(path):
    records = {}
    with path.open(encoding="utf-8-sig") as source:
        for number, line in enumerate(source, 1):
            row = line.rstrip("\r\n")
            parts = row.split(" | ")
            family, _, key = parts[0].partition(" ")
            if family not in {"FILE", "REG", "FUSION"} or not key or len(parts) != (4 if family == "REG" else 3):
                raise ValueError(f"{path.name}:{number}: invalid capture row")
            if family in {"REG", "FUSION"}:
                identity = (family, key, parts[1], parts[2] == "KEY" if family == "REG" else row)
            else:
                identity = (family, key)
            if identity in records:
                raise ValueError(f"{path.name}:{number}: duplicate capture item")
            records[identity] = row
    return records


def group(item):
    family, path = item[:2]
    if family == "FILE":
        return f"FILE {path.rpartition('/')[0] or '.'}"
    if family == "FUSION":
        return "FUSION"
    hive, key = path.split("\\", 1)
    com = com_group(key)
    if com:
        root, _ = com.rsplit("\\", 1)
        if root.rsplit("\\", 1)[-1] not in COM_FAMILIES:
            root += r"\progids"
        return f"REG {hive}\\{root}"
    parts = key.split("\\")
    count = 4 if parts[:2] == ["software", "wow6432node"] else 3
    return f"REG {hive}\\" + "\\".join(parts[:count])


def comparison(before, after):
    groups = defaultdict(list)
    for item in sorted(before.keys() | after.keys()):
        old, new = before.get(item), after.get(item)
        if old != new:
            heading = group(item)
            if old is None:
                groups[heading].append(("added", f"+ {new}"))
            elif new is None:
                groups[heading].append(("removed", f"- {old}"))
            else:
                groups[heading].append(("changed", f"~ {old}\n  -> {new}"))
    return groups


def report(groups, stream, limit=None):
    for heading, changes in sorted(groups.items()):
        counts = [sum(kind == status for kind, _ in changes) for status in ("added", "removed", "changed")]
        print(f"[{heading}] added={counts[0]} removed={counts[1]} changed={counts[2]}", file=stream)
        for _, row in changes[:limit]:
            print(row, file=stream)
        if limit is not None and len(changes) > limit:
            print(f"... {len(changes) - limit} more changes", file=stream)
    if not groups:
        print("No differences.", file=stream)


def open_output(path):
    return open(path, "x", encoding="utf-8", newline="\n",
                opener=lambda name, flags: os.open(name, flags, 0o600))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    collect = subparsers.add_parser("capture")
    collect.add_argument("prefix", type=Path)
    collect.add_argument("phase", choices=PHASES)
    collect.add_argument("--output", type=Path)
    collect.add_argument("--fusion-log", choices=("collect",))
    compare = subparsers.add_parser("compare")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    compare.add_argument("--details", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "capture":
            output = args.output or Path(f"companion-capture-{args.phase}.txt")
            rows = sorted(set(capture(args.prefix, args.fusion_log == "collect")), key=ordinal)
            with open_output(output) as stream:
                stream.writelines(row + "\n" for row in rows)
            print(f"{args.phase}: {len(rows)} items written")
        else:
            groups = comparison(read_capture(args.before), read_capture(args.after))
            if args.details:
                with open_output(args.details) as stream:
                    report(groups, stream)
            report(groups, sys.stdout, limit=40)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"companion-capture: {exc}\n")


if __name__ == "__main__":
    main()
