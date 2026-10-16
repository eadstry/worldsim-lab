"""Shared per-page explanatory layout; keeps each source chart's physical size."""
import json,re
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
P=Path(__file__).resolve().parent
EXPLANATIONS=json.loads((P/'page-explanations.json').read_text())
FIELDS=[('how','怎么做的'),('why','这样做的意义'),('result','当前结论'),('reading','读图与术语')]
LAYOUT_CHECKS={}

def explanatory_footer(fig,name,page,section,count):
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer()
    w,h=fig.get_size_inches()
    # Save an unchanged chart for the HTML reader; prose there remains native text.
    (P/'chart-images').mkdir(exist_ok=True)
    fig.savefig(P/'chart-images'/f'{name}.png',dpi=160)
    fp=FontProperties(family='WenQuanYi Micro Hei',size=12)
    max_width=(.93*w-1.28)*fig.dpi
    def width(s):return renderer.get_text_width_height_descent(s,fp,False)[0]
    def wrap(s):
        lines=[];line=''
        for token in re.findall(r'[A-Za-z0-9_./%+–→-]+|\s+|.',s):
            if line and width(line+token)>max_width:
                # Keep closing punctuation with the preceding text.
                if token in '，。；：、！？）】》%':
                    lines.append(line+token);line=''
                else:
                    lines.append(line.rstrip());line=token.lstrip()
            else:line+=token
        if line:lines.append(line.rstrip())
        assert all(width(s)<max_width+18 for s in lines),(name,lines)
        return lines
    blocks=[(label,wrap(EXPLANATIONS[name][key])) for key,label in FIELDS]
    line_height=19/72
    content_height=sum(len(lines)*line_height+.14 for _,lines in blocks)
    extra=max(4.2,1.05+content_height+.18)
    total=h+extra
    axes=[(ax,ax.get_position().frozen()) for ax in fig.axes]
    texts=[(t,t.get_position()) for t in fig.texts]
    fig.set_size_inches(w,total)
    for ax,b in axes:ax.set_position([b.x0,(b.y0*h+extra)/total,b.width,b.height*h/total])
    for t,(x,y) in texts:t.set_position((x,(y*h+extra)/total))
    fig.add_artist(plt.Line2D([.03,.97],[(extra-.06)/total]*2,transform=fig.transFigure,color='#c4ccd7',lw=1))
    footer=[]
    footer.append(fig.text(.035,(extra-.25)/total,f'{page:02d} / {count}  ·  {section}',fontsize=10,color='#197c88',va='top'))
    footer.append(fig.text(.035,(extra-.57)/total,EXPLANATIONS[name]['title'],fontsize=14,fontweight='bold',color='#182b40',va='top'))
    top=extra-1.02
    bounds=[]
    for label,lines in blocks:
        label_text=fig.text(.035,top/total,label,fontsize=11,fontweight='bold',color='#197c88',va='top')
        body=fig.text(.035+1.28/w,top/total,'\n'.join(lines),fontsize=12,color='#24384d',va='top',linespacing=1.5)
        footer.extend([label_text,body]);bounds.append(body)
        top-=len(lines)*line_height+.14
    fig.canvas.draw();renderer=fig.canvas.get_renderer()
    for t in footer:
        b=t.get_window_extent(renderer)
        assert b.x0>=0 and b.x1<fig.bbox.x1-5 and b.y0>8,(name,'footer outside canvas',b)
    for earlier,later in zip(bounds,bounds[1:]):
        assert earlier.get_window_extent(renderer).y0>later.get_window_extent(renderer).y1,(name,'paragraph overlap')
    LAYOUT_CHECKS[name]={'footer_inches':round(extra,3),'chart_inches':[float(w),float(h)],'paragraph_lines':[len(lines) for _,lines in blocks],'footer_inside_canvas':True,'paragraphs_do_not_overlap':True}
