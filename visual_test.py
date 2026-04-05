#!/usr/bin/env python3
"""
Quick visual test - Shows both themes side by side in terminal
"""
import sys
sys.path.insert(0, '/home/sherzod/Projects/pos-desktop-pyqt')

from ui.styles import THEME_COLORS

def color_block(hex_color, width=10):
    """Create a colored block using ANSI escape codes (approximation)"""
    # Convert hex to RGB
    hex_color = hex_color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    # Return ANSI colored text
    return f"\033[48;2;{r};{g};{b}m{' ' * width}\033[0m"

print("\n" + "="*70)
print("THEME VISUAL COMPARISON")
print("="*70)

print(f"\n{'Element':<25} {'Light Mode':<25} {'Dark Mode':<25}")
print("-"*70)

light = THEME_COLORS['light']
dark = THEME_COLORS['dark']

for key in ['bg_primary', 'bg_secondary', 'text_primary', 'text_secondary', 
            'accent', 'border', 'success', 'error']:
    if key in light and key in dark:
        light_color = color_block(light[key])
        dark_color = color_block(dark[key])
        print(f"{key:<25} {light_color} {light[key]:<12} {dark_color} {dark[key]}")

print("\n" + "="*70)
print("If you see colored blocks above, themes are different!")
print("="*70 + "\n")
