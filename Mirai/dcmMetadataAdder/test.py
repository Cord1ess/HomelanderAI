import os
import pydicom

files = ["RIGHT_MLO.dcm", "RIGHT_CC.dcm", "LEFT_CC.dcm", "LEFT_MLO.dcm"]
base_dir = r"D:\mirai\test"

for file_name in files:
    file_path = os.path.join(base_dir, file_name)
    print(f"--- {file_name} ---")

    if not os.path.exists(file_path):
        print("File not found!\n")
        continue

    ds = pydicom.dcmread(file_path)
    print("Laterality:", getattr(ds, "ImageLaterality", "Missing"))
    print("ViewPosition:", getattr(ds, "ViewPosition", "Missing"))
    print("SeriesDescription:", getattr(ds, "SeriesDescription", "Missing"))
    print("Manufacturer:", getattr(ds, "Manufacturer", "Missing"))
    print()