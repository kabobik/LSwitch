#!/usr/bin/env python3
"""
Генератор иконки LSwitch в PNG с адаптацией под тему
"""

try:
    from PIL import Image, ImageDraw, ImageFont
    import sys
    
    def create_icon(size=64, is_dark_theme=False):
        """Создает иконку для светлой или темной темы"""
        # Прозрачный фон
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Цвет в зависимости от темы
        color = (255, 255, 255, 255) if is_dark_theme else (0, 0, 0, 255)
        
        # Корпус клавиатуры
        margin = size // 8
        kb_height = size // 2
        kb_y = size // 3
        draw.rounded_rectangle(
            [margin, kb_y, size - margin, kb_y + kb_height],
            radius=size // 16,
            outline=color,
            width=2
        )
        
        # Клавиши (3 ряда)
        key_size = size // 12
        key_margin = size // 24
        start_x = margin + key_margin
        start_y = kb_y + key_margin
        
        for row in range(3):
            keys_in_row = 7 if row < 2 else 5
            for col in range(keys_in_row):
                x = start_x + col * (key_size + 2)
                y = start_y + row * (key_size + 2)
                draw.rectangle(
                    [x, y, x + key_size, y + key_size],
                    fill=color
                )
        
        # Пробел
        spacebar_width = size // 2
        spacebar_height = key_size
        spacebar_x = (size - spacebar_width) // 2
        spacebar_y = start_y + 3 * (key_size + 2)
        draw.rectangle(
            [spacebar_x, spacebar_y, spacebar_x + spacebar_width, spacebar_y + spacebar_height],
            fill=color
        )
        
        # Текст Ru/En
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size // 6)
        except:
            font = ImageFont.load_default()
        
        text_y = margin
        draw.text((margin + 2, text_y), "Ru", fill=color, font=font)
        draw.text((size - margin - size // 5, text_y), "En", fill=color, font=font)
        
        # Стрелки переключения
        arrow_y = margin + size // 8
        arrow_center_x = size // 2
        arrow_size = size // 16
        
        # Стрелка вверх
        draw.polygon([
            (arrow_center_x, arrow_y),
            (arrow_center_x - arrow_size, arrow_y + arrow_size),
            (arrow_center_x + arrow_size, arrow_y + arrow_size)
        ], fill=color)
        
        # Стрелка вниз
        arrow_y2 = arrow_y + arrow_size * 2
        draw.polygon([
            (arrow_center_x, arrow_y2 + arrow_size),
            (arrow_center_x - arrow_size, arrow_y2),
            (arrow_center_x + arrow_size, arrow_y2)
        ], fill=color)
        
        return img
    
    if __name__ == '__main__':
        # Создаем обе версии
        light_icon = create_icon(64, is_dark_theme=False)
        dark_icon = create_icon(64, is_dark_theme=True)
        
        light_icon.save('lswitch-light.png')
        dark_icon.save('lswitch-dark.png')
        
        # Создаем основную (светлую по умолчанию)
        light_icon.save('lswitch.png')
        
        print("✓ Иконки созданы: lswitch.png, lswitch-light.png, lswitch-dark.png")
        
except ImportError:
    print("⚠️  Установите pillow для генерации иконок: pip3 install pillow")
    print("   Или используйте SVG иконку")
