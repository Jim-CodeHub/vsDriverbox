import os
from PIL import Image

def convert_png_to_ico(icon_dir):
    """
    Converts all PNG files in the specified directory to multi-resolution ICO files.
    Keeps the original PNG files.
    """
    if not os.path.exists(icon_dir):
        print(f"Directory not found: {icon_dir}")
        return

    # Standard ICO sizes for Windows
    icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

    png_files = [f for f in os.listdir(icon_dir) if f.lower().endswith('.png')]
    
    if not png_files:
        print("No PNG files found to convert.")
        return

    print(f"Found {len(png_files)} PNG files. Starting conversion...")

    for png_file in png_files:
        png_path = os.path.join(icon_dir, png_file)
        ico_name = os.path.splitext(png_file)[0] + '.ico'
        ico_path = os.path.join(icon_dir, ico_name)

        try:
            with Image.open(png_path) as img:
                # Convert to RGBA if necessary
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                
                # Save as ICO with multiple sizes
                img.save(ico_path, format='ICO', sizes=icon_sizes)
                print(f"Successfully converted: {png_file} -> {ico_name}")
        except Exception as e:
            print(f"Failed to convert {png_file}: {e}")

if __name__ == "__main__":
    # Use the absolute path provided in the environment or context
    target_dir = r"c:\Users\Jim\PycharmProjects\vsDriverbox\src\icon"
    convert_png_to_ico(target_dir)
