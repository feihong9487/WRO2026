/* 理香板（改良版・八邊形切角）— Bambu Lab X1 · 0.4mm 噴頭
 * 需求：中央圓形 M3.5 香孔區、其他實心、四角套燃燒艙定位榫、要塞得進集煙罩、
 *       四角半口(不要尖腳 prong)。
 *
 * ★會不會卡集煙罩★ 集煙罩直筒段內腔 = CHMB 156 − 2×WALL 2.4 = 151.2mm。
 *   板邊到邊取 148（每邊留 1.6mm 餘裕）→ 確定塞得進、不頂內壁。
 * ★四角★ 定位榫是絕對位置：距 156 邊 7.9mm → 中心 ±70.1（不隨板寬變）。
 *   用 45° 把四角切掉,切線 |x|+|y|=140.2 正好過榫中心 → 榫孔變成半圓開口(半口),
 *   外側料被切掉、不留尖腳,也讓開集煙罩。
 * 列印：平放、孔朝上、免支撐。
 */
BOARD         = 148;         // 邊到邊寬（< 集煙罩內腔 151.2，留餘裕）
THICK         = 6;
FIELD_D       = 117;         // 中央圓形香孔區直徑
HOLE_D        = 3.6;         // 香孔（印出≈3.5=M3.5）
WALL_BETWEEN  = 1.4;         // 香孔洞壁
PITCH         = HOLE_D + WALL_BETWEEN;   // 5.0
TENON_POS     = 70.1;        // 榫中心絕對座標 = 156/2 − 7.9
CORNER_HOLE_D = 8.6;         // 套定位榫（8 + 間隙）
CUT           = TENON_POS*2; // 45° 切角線,過榫中心 = 140.2（半口）
OVER          = 1;
$fn           = 20;

module incense_board(){
  h = BOARD/2;               // 74
  c = CUT - h;               // 66.1：切角後八邊形的頂點座標
  fr = FIELD_D/2; hlim = fr - HOLE_D/2;
  row_h = PITCH*sin(60); nrow = ceil(fr/row_h); ncol = ceil(fr/PITCH);
  difference(){
    // 八邊形板（方板切四角）
    linear_extrude(THICK)
      polygon([[h,c],[c,h],[-c,h],[-h,c],[-h,-c],[-c,-h],[c,-h],[h,-c]]);
    // 中央圓形香孔區（六角密排）
    for(iy=[-nrow:nrow]){
      y = iy*row_h; xoff = (iy%2)*PITCH/2;
      for(ix=[-ncol:ncol]){
        x = ix*PITCH + xoff;
        if (sqrt(x*x+y*y) <= hlim) translate([x,y,-OVER]) cylinder(h=THICK+2*OVER, d=HOLE_D);
      }
    }
    // 四角定位榫孔（外側已被切角切掉 → 自動變半口）
    for(sx=[-1,1], sy=[-1,1])
      translate([sx*TENON_POS, sy*TENON_POS, -OVER])
        cylinder(h=THICK+2*OVER, d=CORNER_HOLE_D, $fn=48);
  }
}
incense_board();
