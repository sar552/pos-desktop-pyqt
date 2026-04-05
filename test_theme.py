#!/usr/bin/env python3
"""
Theme Test Script - Verify that light and dark themes are visually different
"""
import sys
sys.path.insert(0, '/home/sherzod/Projects/pos-desktop-pyqt')

from ui.theme_manager import ThemeManager
from ui.styles import get_stylesheet, THEME_COLORS

print("=" * 60)
print("THEME SYSTEM TEST")
print("=" * 60)

# Test 1: Color Palettes
print("\n1. COLOR PALETTES:")
print("-" * 60)

light_colors = THEME_COLORS['light']
dark_colors = THEME_COLORS['dark']

print(f"\n{'Color Key':<20} {'Light Mode':<15} {'Dark Mode':<15}")
print("-" * 60)

for key in light_colors:
    light_val = light_colors[key]
    dark_val = dark_colors[key]
    match = "✓ SAME" if light_val == dark_val else "✗ DIFFERENT"
    print(f"{key:<20} {light_val:<15} {dark_val:<15} {match}")

# Test 2: Stylesheet Generation
print("\n2. STYLESHEET GENERATION:")
print("-" * 60)

light_style = get_stylesheet('light')
dark_style = get_stylesheet('dark')

print(f"Light stylesheet length: {len(light_style)} characters")
print(f"Dark stylesheet length:  {len(dark_style)} characters")
print(f"Stylesheets identical:   {'YES ❌' if light_style == dark_style else 'NO ✓'}")

# Test 3: Sample Color Extraction
print("\n3. VISUAL DIFFERENCE SAMPLES:")
print("-" * 60)

print(f"\nBackground Primary:")
print(f"  Light: {light_colors['bg_primary']}")
print(f"  Dark:  {dark_colors['bg_primary']}")

print(f"\nText Primary:")
print(f"  Light: {light_colors['text_primary']}")
print(f"  Dark:  {dark_colors['text_primary']}")

print(f"\nAccent Color:")
print(f"  Light: {light_colors['accent']}")
print(f"  Dark:  {dark_colors['accent']}")

# Test 4: Check differences
print("\n4. DIFFERENCE ANALYSIS:")
print("-" * 60)

different_count = 0
same_count = 0

for key in light_colors:
    if light_colors[key] != dark_colors[key]:
        different_count += 1
    else:
        same_count += 1

print(f"Different colors: {different_count}/{len(light_colors)}")
print(f"Same colors:      {same_count}/{len(light_colors)}")

if different_count > len(light_colors) * 0.7:
    print("\n✓ PASS: Themes are visually distinct (>70% different)")
else:
    print(f"\n❌ FAIL: Themes too similar (only {different_count}/{len(light_colors)} different)")

# Test 5: ThemeManager
print("\n5. THEME MANAGER TEST:")
print("-" * 60)

try:
    # Test getting colors
    colors = ThemeManager.get_theme_colors('light')
    print(f"✓ Can get light theme colors: {len(colors)} keys")
    
    colors = ThemeManager.get_theme_colors('dark')
    print(f"✓ Can get dark theme colors: {len(colors)} keys")
    
    # Test login styles
    login_light = ThemeManager.get_login_styles('light')
    print(f"✓ Can get light login styles: {len(login_light)} keys")
    
    login_dark = ThemeManager.get_login_styles('dark')
    print(f"✓ Can get dark login styles: {len(login_dark)} keys")
    
    print("\n✓ ALL TESTS PASSED")
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
