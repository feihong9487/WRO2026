# CAD_LOOP.md — 機構設計的 Loop Engineering

> 給 Claude Code 與人類共同遵守。與 CLAUDE.md 併同閱讀。
> 核心前提：**Claude 看不到你的 3D 模型**。所以這套流程不是「讓 AI 畫 CAD」，
> 而是把設計拆成「可自動判定」與「必須人來看」兩部分，各自誠實對待。

---

## 1. 三層迴路

| 層 | 驗證器 | 速度 | 抓得到 | 抓不到 |
|---|---|---|---|---|
| **L1 參數規則** | `pytest test_mech_design.py` | 毫秒 | 尺寸衝突、材料誤用、間隙不足、預算超支、過濾鏈順序 | 任何形狀相關的事 |
| **L2 幾何檢查** | `python3 verify_stl.py <檔案>` | 秒 | 破面、外框超尺寸、通孔數不符、體積異常、法向量錯亂 | 是否好用、應力、外觀 |
| **L3 實體行為** | 人 | 天 | 熱變形、氣流、插香手感、耐久 | — |

L1 是最被低估的一層：**多數機構錯誤其實是參數之間的算術**。「孔距 − 孔徑 ≥ 最小壁厚」不需要幾何就能驗證，而它正是最常出錯的地方。建模之前就先把 L1 跑綠。

## 2. 工作流

```
mech_params.py          ← 唯一真相來源（Onshape 變數、報告數據都以它為準）
      │
      ├─ pytest test_mech_design.py      L1：改參數 → 秒級知道有無違規
      │
      ├─ 【人】在 Onshape Variable Studio 填入相同數值 → 建模
      │
      ├─ 【人】匯出 STL（Onshape：Export → STL → Fine）
      │
      ├─ python3 verify_stl.py part.stl                        L2：幾何回頭核對參數
      │
      └─ 【人】列印 → 實測 → 把量到的真值寫回 mech_params.py，
                            並把對應的 *_MEASURED 改成 True
```

改設計時的正確順序永遠是：**先改 `mech_params.py` → 跑 L1 → 才動 Onshape**。反過來做，模型與參數會分岔，L2 就永遠對不上。

## 3. Onshape 對接

- 在 Variable Studio 建立與 `mech_params.py` 同名的變數，草圖尺寸全部引用變數，不要寫死數字。
- 匯出 STL 時解析度選 Fine；粗糙的三角化會讓 L2 的體積比對失準。
- 第二期可用 Onshape REST API 直接讀取變數值與質量屬性做自動比對，省掉人工填數值這一步。現階段投報率不高，先不做。

## 4. 給 Claude Code 的規則

### 4.1 可以做
- 依需求修改 `mech_params.py` 的**非紅線**參數，並跑 L1 驗證
- 新增設計規則測試（例如新零件的干涉檢查）
- 執行 `verify_stl.py` 並診斷失敗原因
- 用參數計算衍生量（用料、力學估算、陣列排布）
- 產生給人在 Onshape 操作的建模步驟說明

### 4.2 禁止（reward hacking 防線）
- ❌ 放寬壁厚、氣隙、耐熱等安全與可製造性下限來讓測試通過
- ❌ 把近爐零件的材料改成 PLA，或把零件標成 `near_censer=False` 來規避禁 PLA 規則
- ❌ 調換 `FILTER_CHAIN` 順序（金屬紗網必須在 HEPA 之前）
- ❌ 修改 `test_mech_design.py` 的斷言，或放寬 `verify_stl.py` 的容差
- ❌ 把 `*_MEASURED` 旗標改成 `True` —— **只有人實際量過才能改**
- ❌ 聲稱任何需要實體列印或實測的事項「已驗證」

參數之間衝突到無解時，正確反應是回報衝突並提出取捨方案，讓人決定。例如：耐熱與成本衝突時，選項是換材料（貴）、加大氣隙（體積變大）、或降規使用情境——這是設計決策，不是 agent 該自己選的。

### 4.3 硬體邊界（永遠人在迴路）
以下**無法**由任何自動檢查取代，agent 不得宣稱完成：
熱變形實測｜氣流與抽排效能｜插香手感與人因｜列印件強度與耐久｜外觀與文化適切性（廟方觀感）。

## 5. 常用指令

```bash
# L1：參數規則（建模前先跑綠）
python3 -m pytest test_mech_design.py -q
python3 -m pytest test_mech_design.py -q -k PLA        # 只跑材料相關

# L2：幾何驗證（Onshape 匯出後）
pip install trimesh numpy --break-system-packages
python3 verify_stl.py <零件>.stl

# 一次跑全部軟體迴路（FSM + 機構）
python3 -m pytest -q

# 查看還有哪些數值沒實測
python3 -c "import mech_params as P; print(P.unmeasured_items())"
```

## 6. 待辦：把估計值換成實測值

`mech_params.py` 中所有 `*_MEASURED = False` 的項目都是估計值。優先量測順序：

1. **香爐內徑與深度** — retrofit 模組要架在真爐上，量錯整個外形重來
2. **近爐區實際溫度** — 用你們的 MAX6675 直接量，同時驗證禁 PLA 區範圍與聯鎖門檻
3. **風扇靜壓與啟動突波** — 決定過濾鏈選型與電源餘裕的真實性
4. **霧化模組實際電流** — 展示機電流預算的最後一個估值
5. **感測器艙實際溫度** — SCD41 工作上限 60°C 的安全餘裕

每量到一項就更新數值、把旗標改 True、重跑 L1。全部改完之後，報告中相關數字才能從「設計目標」變成實測值。

## 7. 可拍的證據

- L1 測試全綠的截圖（規則名稱本身就是設計規範的白話版）
- `verify_stl.py` 通過的輸出 ＋ 對應的 Onshape 模型截圖並排
- 「通孔數由虧格推算 = 設計值」那一行 —— 這是模型與規格一致的硬證據
- 待實測清單截圖：證明你們清楚知道哪些是估計值，這在答詢時是加分而非扣分
