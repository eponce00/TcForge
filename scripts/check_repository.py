"""Source integrity checks. This does not compile or execute Structured Text."""

from pathlib import Path
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def check_reference_versions(document, lock):
    """Check declared direct references against pins; does not resolve transitives."""
    errors = []
    pinned = dict(lock.get("resolvedVendorLibraries", {}))
    pinned.update(
        TcForge=lock.get("libraryVersion"),
        TcForgeExample=lock.get("libraryVersion"),
        TcUnit=lock.get("tcunitVersion"),
    )
    for node in document.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag not in ("PlaceholderReference", "LibraryReference"):
            continue
        if tag == "PlaceholderReference":
            name = node.get("Include", "")
            resolution = next(
                (
                    child.text or ""
                    for child in node
                    if child.tag.rsplit("}", 1)[-1] == "DefaultResolution"
                ),
                "",
            )
        else:
            resolution = node.get("Include", "")
            name = resolution.split(",", 1)[0].strip()
        match = re.fullmatch(r"([^,]+),\s*([^\s(]+)\s*\([^)]*\)", resolution.strip())
        expected = pinned.get(name)
        if not expected:
            errors.append(f"No toolchain pin for direct reference {name}")
        elif (
            match is None
            or match.group(1).strip()
            not in (
                {name, "[" + name + "]"}
                if name in ("TcForge", "TcForgeExample")
                else {name}
            )
            or match.group(2) != expected
        ):
            errors.append(
                f"Direct reference {name} does not match toolchain version {expected}: {resolution}"
            )
    return errors


def check_development_layout(root):
    """Prevent installed-reference fallback and accidental multi-application test deployment."""
    errors = []
    profiles = {
        "TcForge": {"TcForge", "TcForgeExample", "Testing", "Simulation"},
        "TcForge.Example": {"TcForge", "TcForgeExample"},
        "TcForge.Tests": {"TcForge", "TcForgeExample", "Testing"},
        "TcForge.Simulation": {"TcForge", "TcForgeExample", "Simulation"},
    }
    for name, expected in profiles.items():
        path = root / "TwinCAT" / (name + ".tsproj")
        try:
            doc = ET.parse(path)
            projects = doc.findall(".//Plc/Project")
            if (
                len(projects) != len(expected)
                or {p.get("Name") for p in projects} != expected
            ):
                errors.append(f"{name}: incorrect PLC project membership")
            tasks = doc.findall(".//System/Tasks/Task")
            for field in ("Id", "Priority", "AmsPort"):
                values = [task.get(field) for task in tasks]
                if len(values) != len(set(values)):
                    errors.append(f"{name}: duplicate system task {field}")
            for project in projects:
                plc = ET.parse(
                    path.parent / project.get("PrjFilePath").replace("\\", "/")
                )
                if (
                    project.get("Name") == "TcForgeExample"
                    and plc.findtext(".//{*}VirtualLibrary") != "true"
                ):
                    errors.append(f"{name}: example must enable referenced-library use")
                if project.get("Name") == "TcForge" or (
                    project.get("Name") == "TcForgeExample"
                    and name in ("TcForge.Tests", "TcForge.Simulation")
                ):
                    if project.find("Instance") is not None:
                        errors.append(
                            f"{name}: source libraries must not have runtime instances"
                        )
                    guid = plc.findtext(".//{*}ProjectGuid", "").upper()
                    solution = (
                        path.with_suffix(".sln").read_text(encoding="utf-8-sig").upper()
                    )
                    for configuration in ("DEBUG", "RELEASE"):
                        for platform in ("TWINCAT OS (X64)", "TWINCAT RT (X64)"):
                            if (
                                f"{guid}.{configuration}|{platform}.ACTIVECFG"
                                not in solution
                            ):
                                errors.append(
                                    f"{name}: source library missing explicit solution configuration"
                                )
                    if any(
                        guid in line and ".BUILD.0" in line
                        for line in solution.splitlines()
                    ):
                        errors.append(
                            f"{name}: source libraries must not build boot projects"
                        )
                    if plc.findtext(".//{*}VirtualLibrary") != "true":
                        errors.append(
                            f"{name}: {project.get('Name')} must enable referenced-library use"
                        )
                    if project.get("Name") == "TcForge":
                        continue
                refs = plc.findall(".//{*}PlaceholderReference[@Include='TcForge']")
                if len(refs) != 1 or not (
                    refs[0].findtext("{*}DefaultResolution") or ""
                ).startswith("[TcForge], "):
                    errors.append(
                        f"{name}: {project.get('Name')} must reference TcForge source"
                    )
        except (OSError, ET.ParseError, TypeError) as exc:
            errors.append(f"{name}: invalid development profile: {exc}")
    return errors


def check(root=ROOT, release=False, report=None, build_evidence=None, library=None):
    errors = check_development_layout(root)
    documents = {}
    for path in (root / "TwinCAT").rglob("*"):
        if path.suffix.lower() not in {
            ".tcpou",
            ".tcdut",
            ".tcio",
            ".tcgvl",
            ".tctto",
            ".plcproj",
            ".tsproj",
        }:
            continue
        try:
            data = path.read_bytes()
            if data.startswith(b"\xef\xbb\xbf"):
                errors.append(f"{path}: UTF-8 BOM")
            documents[path] = ET.fromstring(data)
        except (ET.ParseError, UnicodeError) as exc:
            errors.append(f"{path}: {exc}")
    for path, doc in documents.items():
        includes = []
        for node in doc.iter():
            tag = node.tag.rsplit("}", 1)[-1]
            if tag == "Compile":
                relative = node.get("Include", "")
                includes.append(relative.lower())
                if not (path.parent / relative.replace("\\", "/")).is_file():
                    errors.append(f"{path}: missing compile input {relative}")
            if tag == "POU":
                declaration = node.findtext("Declaration", "")
                declaration = re.sub(
                    r"//[^\n]*|\(\*.*?\*\)", "", declaration, flags=re.S
                )
                if re.search(r"\bEND_VAR\s+[A-Za-z_]\w*\s*:", declaration):
                    errors.append(f"{path}: declaration outside VAR block")
                metadata_seen = False
                for child in node:
                    if child.tag == "LineIds":
                        metadata_seen = True
                    elif metadata_seen:
                        errors.append(
                            f"{path}: code after LineIds metadata is ignored by XAE"
                        )
                names = [m.get("Name", "").lower() for m in node.findall("Method")]
                if len(names) != len(set(names)):
                    errors.append(f"{path}: duplicate methods")
                if node.findall("Folder/Method"):
                    errors.append(f"{path}: methods nested inside folders")
            if tag == "DUT":
                declaration = node.findtext("Declaration", "")
                declaration = re.sub(
                    r"//[^\n]*|\(\*.*?\*\)", "", declaration, flags=re.S
                )
                if re.search(r"\bEND_STRUCT\s+(?!END_TYPE\b)\S", declaration, re.I):
                    errors.append(f"{path}: declaration outside STRUCT")
            if tag == "POU":
                if "TcForge/Modules" in path.as_posix():
                    declaration = node.findtext("Declaration", "")
                    declaration = re.sub(
                        r"//[^\n]*|\(\*.*?\*\)", "", declaration, flags=re.S
                    )
                    if re.search(r"\bAT\s+%[IQ]", declaration, re.I):
                        errors.append(
                            f"{path}: library block allocates application hardware"
                        )
                    for method in node.findall("Method"):
                        decl = method.findtext("Declaration", "")
                        body = method.findtext("Implementation/ST", "")
                        name = method.get("Name", "")
                        commands = {
                            "Ack",
                            "Reset",
                            "Home",
                            "Start",
                            "Stop",
                            "Abort",
                            "Pause",
                            "Proceed",
                            "Retry",
                            "Advance",
                            "Retract",
                            "SetOn",
                            "SetOff",
                            "SetValue",
                            "ForceSafe",
                        }
                        if name in commands and re.search(r"\beRequester\s*:", decl):
                            statements = re.sub(
                                r"//[^\n]*|\(\*.*?\*\)", "", body, flags=re.S
                            ).strip()
                            if not statements.startswith(
                                name + " := F_ValidateRequester("
                            ):
                                errors.append(
                                    f"{path}: {name} must validate identity before command logic"
                                )
                        if "TcRpcEnable" in decl:
                            if (
                                not method.get("Name", "").startswith("Operator")
                                or "eRequester :" in decl
                            ):
                                errors.append(
                                    f"{path}: RPC must use a fixed-identity Operator wrapper"
                                )
                            body = method.findtext("Implementation/ST", "")
                            expected = (
                                "_operatorMailbox.GetResult("
                                if method.get("Name") == "OperatorCommandResult"
                                else "_operatorMailbox.Submit("
                            )
                            if (
                                expected not in body
                                or "requestId : ULINT" not in decl
                                or "THIS^." in body
                            ):
                                errors.append(
                                    f"{path}: RPC must use the bounded mailbox with a caller request ID"
                                )
                        if method.get("Name") == "_DispatchOperatorCommand":
                            if "E_Requester.OPERATOR" not in method.findtext(
                                "Implementation/ST", ""
                            ):
                                errors.append(
                                    f"{path}: owner dispatch has no fixed operator identity"
                                )
        if len(includes) != len(set(includes)):
            errors.append(f"{path}: duplicate compile inputs")
    # Shared application/support code has one source owner, referenced by all consumers.
    reference_sources = [
        root / "TwinCAT/TcForgeExample/ClampCycle" / name
        for name in ("FB_ReferenceMachine.TcPOU", "E_ReferenceCommand.TcDUT")
    ]
    reference_sources.append(
        root / "TwinCAT/TcForgeExample/Simulation/FB_SimulationBridge.TcPOU"
    )
    for relative in (
        "TwinCAT/Testing.plcproj",
        "TwinCAT/TcForgeExample/TcForgeExample.plcproj",
        "TwinCAT/Simulation.plcproj",
    ):
        project_path = root / relative
        project_doc = documents.get(project_path)
        if project_doc is None:
            errors.append(f"Missing reference consumer {relative}")
            continue
        compiled = [
            (project_path.parent / node.get("Include", "").replace("\\", "/")).resolve()
            for node in project_doc.iter()
            if node.tag.rsplit("}", 1)[-1] == "Compile"
        ]
        for source in reference_sources:
            expected = (
                1 if relative == "TwinCAT/TcForgeExample/TcForgeExample.plcproj" else 0
            )
            if compiled.count(source.resolve()) != expected:
                errors.append(
                    f"{relative}: shared source {source.name} must be owned only by TcForgeExample"
                )
        if relative != "TwinCAT/TcForgeExample/TcForgeExample.plcproj":
            refs = project_doc.findall(
                ".//{*}PlaceholderReference[@Include='TcForgeExample']"
            )
            if len(refs) != 1 or not (
                refs[0].findtext("{*}DefaultResolution") or ""
            ).startswith("[TcForgeExample], "):
                errors.append(
                    f"{relative}: must reference the shared TcForgeExample source library"
                )
    test_project = root / "TwinCAT/TcForge.Tests.tsproj"
    doc = documents.get(test_project)
    if doc is None:
        errors.append("Missing isolated test project")
    else:
        project = doc.find("Project")
        if project.get("TargetNetId"):
            errors.append("Test project contains a fixed target")
        for tag in ["UnrestoredVarLinks", "Io", "Mappings"]:
            if doc.findall(".//" + tag):
                errors.append(f"Test project contains {tag}")
        if doc.find(".//System/Settings") is not None:
            errors.append("Test project contains machine-specific CPU settings")
    simulation = documents.get(root / "TwinCAT/TcForge.Simulation.tsproj")
    if simulation is None:
        errors.append("Missing isolated simulation project")
    else:
        if simulation.find("Project").get("TargetNetId"):
            errors.append("Simulation project contains a fixed target")
        for tag in ("Io", "Mappings", "UnrestoredVarLinks"):
            if simulation.findall(".//" + tag):
                errors.append(f"Simulation project contains {tag}")
        if simulation.find(".//System/Settings") is not None:
            errors.append("Simulation project contains machine-specific CPU settings")
    simulation_plc = root / "TwinCAT/Simulation.plcproj"
    if simulation_plc.exists() and "TcUnit" in simulation_plc.read_text():
        errors.append("Standalone simulation must not depend on TcUnit")
    suites = set()
    count = 0
    main = (root / "TwinCAT/Testing/POUs/MAIN.TcPOU").read_text(encoding="utf-8")
    for path in (root / "TwinCAT/Testing/Tests").glob("*.TcPOU"):
        doc = documents.get(path)
        if doc is None:
            continue
        pou = doc.find("POU")
        if pou is None:
            continue
        suite = pou.get("Name")
        suites.add(suite)
        if not re.search(r":\s*" + re.escape(suite) + r"\s*;", main):
            errors.append(f"{suite}: not instantiated by test MAIN")
        names = re.findall(r"\bTEST\('([^']+)'\)", path.read_text(encoding="utf-8"))
        count += len(names)
        if len(names) != len(set(names)):
            errors.append(f"{suite}: duplicate test names")
    lock = json.loads((root / "toolchain.json").read_text(encoding="utf-8"))
    for path, document in documents.items():
        if path.suffix.lower() == ".plcproj":
            errors.extend(
                f"{path}: {message}"
                for message in check_reference_versions(document, lock)
            )
    for path in [root / "README.md", *(root / "docs").glob("*.md")]:
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            target = target.split("#")[0]
            if target and not (path.parent / target).exists():
                errors.append(f"{path}: broken local link {target}")
    if release:
        from build_evidence import validate_release

        reports = (
            []
            if report is None
            else ([report] if isinstance(report, (str, Path)) else list(report))
        )
        if build_evidence is None or library is None:
            errors.append(
                "Release blocked: provide --build-evidence and --library with fresh bound build/runtime results"
            )
        else:
            try:
                validate_release(root, build_evidence, library, reports)
            except (ValueError, OSError, KeyError, TypeError, ET.ParseError) as exc:
                errors.append(f"Release blocked: {exc}")
        if lock["qualification"] != "verified":
            errors.append("Release blocked: TwinCAT qualification is not verified")
        for name in ["Tc2_Standard", "Tc2_System", "Tc3_Module"]:
            if not lock["resolvedVendorLibraries"].get(name):
                errors.append(f"Release blocked: no resolved version for {name}")
        for path in (root / "TwinCAT").rglob("*.plcproj"):
            if re.search(
                r"<DefaultResolution>[^<]*\*", path.read_text(encoding="utf-8")
            ):
                errors.append(f"Release blocked: wildcard library resolution in {path}")
    return errors, len(documents), len(suites), count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", action="store_true")
    parser.add_argument(
        "--test-report",
        type=Path,
        action="append",
        help="Repeat for bound 1 ms and 10 ms reports",
    )
    parser.add_argument("--build-evidence", type=Path)
    parser.add_argument("--library", type=Path)
    args = parser.parse_args()
    errors, files, suites, tests = check(
        release=args.release,
        report=args.test_report,
        build_evidence=args.build_evidence,
        library=args.library,
    )
    for error in errors:
        print(error, file=sys.stderr)
    print(
        f"{files} XML files; {suites} suites; {tests} test declarations. Source checks only."
    )
    sys.exit(bool(errors))
