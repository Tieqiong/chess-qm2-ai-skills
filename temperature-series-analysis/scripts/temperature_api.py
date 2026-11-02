"""Small API adapters; quantitative temperature-series analysis is still pending."""

API_STATUS = (
    "Temperature API compatibility repaired; detailed analysis is TO BE UPDATED. "
    "Discovery/grid validation, masks/log handling, and exports/memory work are on hold."
)

FIT_PARAMETERS = {
    "peakheight": "peak_height",
    "area": "peak_amplitude",
    "sigma": "peak_sigma",
    "center": "peak_center",
}


def resolve_temperature_axis(td, cut_axis):
    """Resolve physical H/K/L while retaining native-order center/window tuples.

    Mixing layouts needs per-dataset tuple conversion and is deliberately not
    supported by this small compatibility repair. Grid alignment is not checked.
    """
    try:
        from nxs_analysis_tools.reciprocal import resolve_reciprocal_axes
    except ImportError as error:
        raise ImportError(
            "This wrapper requires nxs_analysis_tools with "
            "reciprocal.resolve_reciprocal_axes."
        ) from error

    if not td.temperatures:
        raise ValueError("No matching temperature datasets were loaded.")
    cut_axis = cut_axis.upper()
    if cut_axis not in ("H", "K", "L"):
        raise ValueError(f"Invalid cut axis: {cut_axis}. Choose H, K, or L.")
    reference = None
    for temperature in td.temperatures:
        mapping = resolve_reciprocal_axes(td.datasets[temperature])
        layout = tuple(mapping[axis] for axis in ("H", "K", "L"))
        if reference is None:
            reference = layout
        elif layout != reference:
            raise ValueError(
                f"Mixed reciprocal-axis ordering at {temperature} K is unsupported; "
                "process each native ordering separately. Center/window tuples "
                "must follow the dataset's nxaxes order."
            )
    return reference[("H", "K", "L").index(cut_axis)]
