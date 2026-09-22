import os
import pydicom

folder_path = r"D:\mirai\test"

metadata_map = {
    "RIGHT_MLO.dcm": {"ImageLaterality": "R", "ViewPosition": "MLO", "SeriesDescription": "RIGHT MLO"},
    "RIGHT_CC.dcm":  {"ImageLaterality": "R", "ViewPosition": "CC",  "SeriesDescription": "RIGHT CC"},
    "LEFT_CC.dcm":   {"ImageLaterality": "L", "ViewPosition": "CC",  "SeriesDescription": "LEFT CC"},
    "LEFT_MLO.dcm":  {"ImageLaterality": "L", "ViewPosition": "MLO", "SeriesDescription": "LEFT MLO"},
}

for filename, tags in metadata_map.items():
    file_path = os.path.join(folder_path, filename)
    if not os.path.exists(file_path):
        continue

    ds = pydicom.dcmread(file_path)

    # Set missing Manufacturer and device tags
    ds.Manufacturer = "MathWorks"
    ds.Modality = "MG"
    ds.SecondaryCaptureDeviceManufacturer = "MathWorks"
    ds.SecondaryCaptureDeviceManufacturerModelName = "MATLAB"

    # Set file-specific tags
    ds.ImageLaterality = tags["ImageLaterality"]
    ds.ViewPosition = tags["ViewPosition"]
    ds.SeriesDescription = tags["SeriesDescription"]

    ds.save_as(file_path)
    print(f"Updated {filename} | Manufacturer: {ds.Manufacturer}")