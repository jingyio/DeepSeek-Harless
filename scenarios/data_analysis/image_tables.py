"""Conservative grid geometry checks; never OCR or fabricate numeric values."""
from __future__ import annotations
from pathlib import Path
import statistics


def image_table_layout(path: Path, *, geometry: bool = False) -> dict | None:
    from PIL import Image
    with Image.open(path) as original:
        if original.width > 10000 or original.height > 10000: return None
        image=original.convert('L')
        image.thumbnail((2200,2200))
    width,height=image.size
    dark=image.point(lambda p: 255 if p<140 else 0)

    def bands(values,threshold):
        runs=[]
        for position,value in enumerate(values):
            if value<threshold: continue
            if runs and position==runs[-1][1]+1:runs[-1][1]=position
            else:runs.append([position,position])
        return runs

    # A single fully ruled rectangular grid only. Sparse charts, prose and
    # irregular/merged cells do not authorize an occupancy check.
    horizontal=bands(list(dark.resize((1,height),Image.Resampling.BOX).getdata()),115)
    if not 4<=len(horizontal)<=1002:return None
    top,bottom=horizontal[0][0],horizontal[-1][1]
    vertical=bands(list(dark.crop((0,top,width,bottom+1)).resize((width,1),Image.Resampling.BOX).getdata()),230)
    if not 3<=len(vertical)<=101:return None
    left,right=vertical[0][0],vertical[-1][1]
    if right-left<width*.4:return None
    for y0,y1 in horizontal:
        if dark.crop((left,y0,right+1,y1+1)).resize((1,1),Image.Resampling.BOX).getpixel((0,0))<225:return None
    gaps=[b[0]-a[1] for a,b in zip(horizontal,horizontal[1:])]
    if min(gaps)<10 or max(gaps)>4*statistics.median(gaps):return None
    empty=[]
    for row,(upper,lower) in enumerate(zip(horizontal,horizontal[1:])):
        for column,(before,after) in enumerate(zip(vertical,vertical[1:]),1):
            box=(before[1]+3,upper[1]+3,after[0]-2,lower[0]-2)
            if box[2]-box[0]<5 or box[3]-box[1]<5:return None
            ink=dark.crop(box).histogram()[255]
            if ink<=3:
                if row==0:return None # No confident single header row.
                empty.append([row,column])
    return {'data_rows':len(horizontal)-2,'columns':len(vertical)-1,'header_rows':1,
            **({'horizontal':horizontal,'vertical':vertical,'image_size':[width,height]} if geometry else {}),
            'empty_cells':empty,'indices':'1-based data row and column',
            'scope':'grid_geometry_and_cell_occupancy_only_not_text_or_numeric_verification'}


def table_row_image(path: Path, start_row: int, row_count: int) -> tuple[dict, bytes]:
    """Expose original pixels in readable strips; never synthesize text or numbers."""
    from PIL import Image
    import io
    layout=image_table_layout(path,geometry=True)
    if not layout:raise ValueError('clear_regular_grid_required_for_row_zoom')
    if type(start_row) is not int or type(row_count) is not int or not 1<=row_count<=10 or not 1<=start_row<=layout['data_rows']:
        raise ValueError('valid_start_row_and_count_1_to_10_required')
    end=min(start_row+row_count-1,layout['data_rows'])
    h,v=layout['horizontal'],layout['vertical']
    with Image.open(path) as original:
        image=original.convert('RGB');image.thumbnail((2200,2200))
        box=(max(0,v[0][0]-2),max(0,h[start_row][0]-2),min(image.width,v[-1][1]+3),min(image.height,h[end+1][1]+3))
        crop=image.crop(box)
        # Preserve each source pixel. A strip occupies its own model image view;
        # duplicating every pixel would inflate inline multimodal requests.
        # Keep sRGB so native attachment admission can preserve these bytes;
        # grayscale PNG would be normalized to a larger lossy JPEG upstream.
        out=io.BytesIO();crop.save(out,format='WEBP',lossless=True,method=6,exact=True)
    return {'start_row':start_row,'end_row':end,'data_rows':layout['data_rows'],
            'media_type':'image/webp','scope':'original_pixels_crop_no_ocr'},out.getvalue()
