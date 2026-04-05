"""
Script to automatically update component styleSheets with theme-aware versions
This runs once to inject theme support into all components
"""
import re

def update_cart_widget():
    """Update cart_widget.py with theme styles"""
    file_path = "ui/components/cart_widget.py"
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Add styles = get_component_styles() after setStyleSheet line
    if "styles = get_component_styles()" not in content:
        content = content.replace(
            'self.setStyleSheet(styles["cart_container"])',
            'styles = get_component_styles()\n        self.setStyleSheet(styles["cart_container"])'
        )
    
    # Replace specific inline styles with theme styles
    replacements = [
        (r'self\.customer_input\.setStyleSheet\("""[^"]*"""\)', 'self.customer_input.setStyleSheet(styles["cart_input"])'),
        (r'self\.customer_clear_btn\.setStyleSheet\("""[^"]*"""\)', 'self.customer_clear_btn.setStyleSheet(styles["cart_button"])'),
        (r'self\.customer_results\.setStyleSheet\("""[^"]*"""\)', 'self.customer_results.setStyleSheet(styles["cart_list"])'),
        (r'cg_label\.setStyleSheet\("color: #[a-fA-F0-9]{6}[^"]*"\)', 'cg_label.setStyleSheet(styles["cart_label"])'),
        (r'self\.cg_mock\.setStyleSheet\("[^"]*"\)', 'self.cg_mock.setStyleSheet(styles["cart_input"])'),
        (r'self\.search_item_input\.setStyleSheet\("[^"]*"\)', 'self.search_item_input.setStyleSheet(styles["cart_input"])'),
        (r'pl_label\.setStyleSheet\("color: #[a-fA-F0-9]{6}[^"]*"\)', 'pl_label.setStyleSheet(styles["cart_label"])'),
        (r'self\.price_list_combo\.setStyleSheet\("[^"]*"\)', 'self.price_list_combo.setStyleSheet(styles["cart_input"])'),
    ]
    
    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content)
    
    with open(file_path, 'w') as f:
        f.write(content)
    
    print(f"✓ Updated {file_path}")

if __name__ == "__main__":
    update_cart_widget()
    print("\n✅ Components updated with theme support!")
