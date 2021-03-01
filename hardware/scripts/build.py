#!/usr/bin/env python
import sys
import os
import pathlib
import shutil
import re
import argparse
import csv
import textwrap
import zipfile


def no_hand_solder(fp):
    # The "HandSolder" suffix seemed to be messing with
    # JLCPCB's automatic part matching, so just drop it.
    return re.sub("Metric_Pad.*_HandSolder", "Metric", fp)


ADJUSTMENTS = [
        ("Q", "SOT-23", 180),
        ("U", "SOT-23-5", 180),
        ("U", "SOT-23-8", 270),
        ("U", "SOT-223-3_TabPin2", 180),
        ("U", "LQFP-48_7x7mm_P0.5mm", 270),
]


def adjust_rot(rot, ref, val, fp):
    for rp, fpm, adj in ADJUSTMENTS:
        if re.fullmatch(rp + r"\d+", ref) and fp == fpm:
            rot += adj
            break
    return rot % 360


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--dnp", action="append")
    parser.add_argument("--preserve", action="store_true")
    args = parser.parse_args(argv[1:])

    project_dir = pathlib.Path(".")
    if not (project_dir / f"{args.project}.pro").exists():
        raise Exception("Run from project directory.")

    gerbers_dir = project_dir / "gerbers"
    assembly_dir = project_dir / "assembly"
    if not args.preserve:
        for d in (gerbers_dir, assembly_dir):
            if d.exists():
                shutil.rmtree(d)

    print(textwrap.dedent("""\
        Manual steps:

        Eeschema:
        - BOM Button -> bom2grouped_csv_jlcpcb
          (make sure output is "%O.bom.csv".)

        Pcbnew:
        - File -> Plot.
        - Ensure "Plot footprint values" is unchecked (if not desired).
        - Ensure "Output directory" is "gerbers/".
        - Click "Plot".
        - Click "Generate Drill Files...".
        - Ensure "Output folder" is "gerbers/".
        - Check "Merge PTH and NPTH holes into one file".
        - Click "Generate Drill File".
        - Close dialogs.
        - File -> Fabrication Outputs -> Footprint Position (.pos) File...
        - Ensure: Format=CSV, Files=Single
        - Click "Generate Position File".

        Misc:
        - View Gerbers if desired.
        - Press Enter to continue.
    """))
    input()

    assembly_dir.mkdir()
    verify_rows = []

    bom_rows = []
    bom_in = project_dir / f"{args.project}.bom.csv"
    with open(bom_in) as handle:
        for row in csv.reader(handle):
            value, ref, footprint, lcsc = row
            if lcsc:
                bom_rows.append(row)
                continue
            footprint = no_hand_solder(footprint)
            if " " in value:
                short_value = re.sub(" .*", "", value)
                verify_rows.append(
                        f"- Value simplified ({ref}): "
                        f'"{value}" -> {short_value}')
                value = short_value
            bom_rows.append((value, ref, footprint, lcsc))
    with open(assembly_dir / "bom.csv", "w") as handle:
        csv.writer(handle).writerows(bom_rows)
    if not args.preserve:
        bom_in.unlink()

    pos_rows = []
    pos_in = gerbers_dir / f"{args.project}-all-pos.csv"
    with open(pos_in) as handle:
        for row in csv.reader(handle):
            ref, val, fp, px, py, rot_s, side = row
            if ref == "Ref":
                pos_rows.append(
                        "Designator,Val,Package,Mid X,Mid Y,RotationLayer"
                        .split(","))
                continue
            if ref in args.dnp:
                continue
            rot = float(rot_s)
            rot = adjust_rot(rot, ref, val, fp)
            pos_rows.append((ref, val, fp, px, py, rot, side))
    with open(assembly_dir / "pos.csv", "w") as handle:
        csv.writer(handle).writerows(pos_rows)
    if not args.preserve:
        pos_in.unlink()

    with zipfile.ZipFile(assembly_dir / "gerbers.zip", "w") as zf:
        for gpath in gerbers_dir.iterdir():
            if gpath.name.endswith("-pos.csv"):
                continue
            with open(gpath, "rb") as handle:
                zf.writestr(gpath.name, gpath.read_bytes())

    with open(assembly_dir / "verify.txt", "w") as handle:
        print()
        print("Verify these values in the automatically matched parts:")
        for row in verify_rows:
            print(row)
            print(row, file=handle)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
