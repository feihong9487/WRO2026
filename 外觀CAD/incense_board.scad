/* 理香板（改良版）— Bambu Lab X1 · 0.4mm 噴頭
 * 方板 + 中央圓形 M3.5 香孔區 + 四角套燃燒艙定位榫的孔
 * 優先序：★印得出來★ > 洞 M3.5 > 洞數
 *
 * 四角孔規格來自 chamber.scad 的 tenons_male（params/common.scad）：
 *   TENON_D=8（頂錐縮 6.8）、TENON_INSET=7.9(=WALL2.4+LEDGE_W11/2)、
 *   CHMB=156、榫孔=8+FIT0.3×2=8.6
 * ★板改 150→156★：150 上角孔離邊僅 0.6mm 會裂；156 對得上 140 見方的榫、
 *   角孔有 3.6mm 壁。中央圓形香孔區沿用原版量到的 ⌀117。
 * 列印：平放,孔朝上,免支撐。
 */
BOARD         = 156;   // = CHMB_W/D，貼合燃燒艙頂、四角對上定位榫
THICK         = 6;     // 板厚（= 榫高，榫穿過剛好齊平）
CORNER_R      = 10;    // = 外殼圓角
FIELD_D       = 117;   // 中央圓形香孔區直徑（量自原版）
HOLE_D        = 3.6;   // 香孔（模型值；印出≈3.5=M3.5）
WALL_BETWEEN  = 1.4;   // 香孔洞壁厚（0.4 噴頭 3.5 條走線）
PITCH         = HOLE_D + WALL_BETWEEN;   // 5.0
TENON_INSET   = 7.9;   // 角孔距板邊
CORNER_HOLE_D = 8.6;   // 套定位榫（8 + 間隙）
OVER          = 1;
$fn           = 20;

module rrect(w,d,h,r){ hull() for(x=[r,w-r],y=[r,d-r]) translate([x,y,0]) cylinder(h=h,r=r,$fn=64); }

module incense_board(){
  fr = FIELD_D/2;
  hole_lim = fr - HOLE_D/2;
  row_h = PITCH*sin(60);
  nrow = ceil(fr/row_h); ncol = ceil(fr/PITCH);
  difference(){
    translate([-BOARD/2,-BOARD/2,0]) rrect(BOARD,BOARD,THICK,CORNER_R);
    // 中央圓形香孔區（六角密排）
    for(iy=[-nrow:nrow]){
      y = iy*row_h; xoff = (iy%2)*PITCH/2;
      for(ix=[-ncol:ncol]){
        x = ix*PITCH + xoff;
        if (sqrt(x*x+y*y) <= hole_lim)
          translate([x,y,-OVER]) cylinder(h=THICK+2*OVER, d=HOLE_D);
      }
    }
    // 四角定位榫孔（★半口：朝外角開口的 U 形槽,不把榫包死、避開集煙罩★）
    for(sx=[-1,1], sy=[-1,1]){
      cx = sx*(BOARD/2 - TENON_INSET);  cy = sy*(BOARD/2 - TENON_INSET);
      ox = sx*(BOARD/2 + 8);            oy = sy*(BOARD/2 + 8);   // 開口延伸到板外緣
      translate([0,0,-OVER]) hull(){
        translate([cx,cy,0]) cylinder(h=THICK+2*OVER, d=CORNER_HOLE_D, $fn=48);
        translate([ox,oy,0]) cylinder(h=THICK+2*OVER, d=CORNER_HOLE_D, $fn=48);
      }
    }
  }
}
incense_board();
