"""诊断CSV文件"""
import pandas as pd
from pathlib import Path

csv_file = Path("data/industry_board_constituents.csv")
df = pd.read_csv(csv_file)

print(f"总行数: {len(df)}")
print(f"\n所有板块名称（前10个）:")
print(df['板块名称'].head(10).tolist())

# 检查是否有重复的板块名称
duplicates = df[df.duplicated(subset=['板块名称'], keep=False)]
if len(duplicates) > 0:
    print(f"\n发现 {len(duplicates)} 个重复的板块:")
    print(duplicates[['板块名称', '成分股数量', '成分股列表']].to_string())
else:
    print("\n没有重复的板块")

# 检查所有包含"食品饮料"的行
food_rows = df[df['板块名称'].str.contains('食品', na=False)]
print(f"\n包含'食品'的板块:")
for idx, row in food_rows.iterrows():
    print(f"  行{idx}: {row['板块名称']} - 成分股数量: {row['成分股数量']}")
    if row['成分股数量'] > 0:
        print(f"    成分股列表前50字符: {str(row['成分股列表'])[:50]}")
    else:
        print(f"    成分股列表: {row['成分股列表']}")
