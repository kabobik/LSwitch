"""Layout compatibility groups for LSwitch.

Defines layout groups for fallback search when the exact target layout
is not available in the system configuration.
"""

from __future__ import annotations

# Layout groups - layouts within the same group are considered compatible
# for fallback purposes (e.g., if 'us' is not available, 'es' can be used
# for Latin character input)
LAYOUT_GROUPS = {
    'latin': ['us', 'en', 'es', 'de', 'fr', 'it', 'pt', 'pl', 'nl', 'se', 'fi', 'no', 'dk', 'cz', 'sk', 'hr', 'ro', 'hu'],
    'cyrillic': ['ru', 'ua', 'by', 'bg', 'sr', 'mk', 'kz'],
    'arabic': ['ar', 'fa', 'ur'],
    'greek': ['gr', 'el'],
    'hebrew': ['il', 'he'],
    'cjk': ['zh', 'ja', 'ko'],
    'thai': ['th'],
    'vietnamese': ['vn'],
}

# Aliases for layout name normalization
LAYOUT_ALIASES = {
    'us': 'en',
    'uk': 'ua',  # Ukrainian
    'gb': 'en',  # British English -> en
}


def normalize_layout_name(name: str) -> str:
    """Normalize layout name to canonical form.
    
    Args:
        name: Layout name (e.g., 'us', 'US', 'en')
        
    Returns:
        Normalized lowercase layout name
    """
    normalized = name.lower().strip()
    return LAYOUT_ALIASES.get(normalized, normalized)


def find_compatible_layout(target: str, available: list) -> str | None:
    """Find a compatible layout from the available list.
    
    First tries to find an exact match (after normalization), then
    searches for any layout from the same compatibility group.
    
    Args:
        target: Target layout name (e.g., 'us', 'en', 'ru')
        available: List of available layouts in the system
        
    Returns:
        Compatible layout name from available list, or None if not found
        
    Examples:
        >>> find_compatible_layout('us', ['en', 'ru'])
        'en'
        >>> find_compatible_layout('es', ['en', 'ru'])
        'en'  # Both in 'latin' group
        >>> find_compatible_layout('ru', ['en', 'ua'])
        'ua'  # Both in 'cyrillic' group
        >>> find_compatible_layout('zh', ['en', 'ru'])
        None  # No compatible layout
    """
    normalized_target = normalize_layout_name(target)
    available_normalized = [normalize_layout_name(l) for l in available]
    
    # Direct match (after normalization)
    if normalized_target in available_normalized:
        # Return the original name from available list
        idx = available_normalized.index(normalized_target)
        return available[idx]
    
    # Search in compatibility groups
    for group_name, layouts in LAYOUT_GROUPS.items():
        if normalized_target in layouts:
            # Target is in this group - find any available layout from same group
            for layout in layouts:
                if layout in available_normalized:
                    idx = available_normalized.index(layout)
                    return available[idx]
    
    return None


def get_layout_group(layout: str) -> str | None:
    """Get the compatibility group name for a layout.
    
    Args:
        layout: Layout name
        
    Returns:
        Group name ('latin', 'cyrillic', etc.) or None if not in any group
    """
    normalized = normalize_layout_name(layout)
    for group_name, layouts in LAYOUT_GROUPS.items():
        if normalized in layouts:
            return group_name
    return None


def are_layouts_compatible(layout1: str, layout2: str) -> bool:
    """Check if two layouts are in the same compatibility group.
    
    Args:
        layout1: First layout name
        layout2: Second layout name
        
    Returns:
        True if both layouts are in the same group
    """
    group1 = get_layout_group(layout1)
    group2 = get_layout_group(layout2)
    
    if group1 is None or group2 is None:
        return False
    
    return group1 == group2
