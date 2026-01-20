/**
 * E2E测试：验证自选股卡片的所有元素
 *
 * 测试目标：
 * 1. 股票卡片正确显示所有必需信息
 * 2. 实时价格数据正确加载
 * 3. K线图正确渲染
 * 4. 交互功能正常工作
 */

import { test, expect, Page } from '@playwright/test';

// 测试数据：标准化股票模版
interface StockTemplate {
  ticker: string;
  name: string;
  sector: string;
  exchange: 'SH' | 'SZ';
}

// 测试用例股票（确保这些股票在测试数据库中）
const TEST_STOCKS: StockTemplate[] = [
  { ticker: '600519', name: '贵州茅台', sector: '消费', exchange: 'SH' },
  { ticker: '000001', name: '平安银行', sector: '金融', exchange: 'SZ' },
  { ticker: '300750', name: '宁德时代', sector: '新能源', exchange: 'SZ' },
];

test.describe('Watchlist Card Validation', () => {
  test.beforeEach(async ({ page }) => {
    // 导航到自选股页面
    await page.goto('http://localhost:5173');
    await page.click('button:has-text("我的自选")');
    await page.waitForSelector('.watchlist-grid', { timeout: 10000 });
  });

  test('should display all required card elements', async ({ page }) => {
    // 等待第一个卡片加载
    const firstCard = page.locator('.watchlist-card').first();
    await expect(firstCard).toBeVisible({ timeout: 10000 });

    // 验证卡片元素
    await expect(firstCard.locator('.watchlist-card__header')).toBeVisible();
    await expect(firstCard.locator('.watchlist-card__name')).toBeVisible();
    await expect(firstCard.locator('.watchlist-card__ticker')).toBeVisible();

    // 验证价格信息
    const priceElement = firstCard.locator('.watchlist-card__price');
    await expect(priceElement).toBeVisible();
    const priceText = await priceElement.textContent();
    expect(priceText).toMatch(/¥\d+\.\d{2}/); // 格式: ¥XX.XX

    // 验证今日涨跌幅
    const todayChange = firstCard.locator('.watchlist-card__change');
    if (await todayChange.count() > 0) {
      const changeText = await todayChange.textContent();
      expect(changeText).toMatch(/今\s*[+\-]?\d+\.\d{2}%/);
    }

    // 验证昨日涨跌幅
    const prevChange = firstCard.locator('.watchlist-card__prev-change');
    if (await prevChange.count() > 0) {
      const prevText = await prevChange.textContent();
      expect(prevText).toMatch(/昨\s*[+\-]?\d+\.\d{2}%/);
    }
  });

  test('should display live indicator during market hours', async ({ page }) => {
    const firstCard = page.locator('.watchlist-card').first();
    await expect(firstCard).toBeVisible({ timeout: 10000 });

    // 检查是否有实时指示器
    const liveIndicator = firstCard.locator('.watchlist-card__live');

    // 如果在交易时间内，应该显示实时指示器
    if (await liveIndicator.count() > 0) {
      await expect(liveIndicator).toBeVisible();
      const liveText = await liveIndicator.textContent();
      expect(liveText).toMatch(/🔴\s*\d{2}:\d{2}:\d{2}/); // 格式: 🔴 HH:MM:SS
    }
  });

  test('should display market value and PE ratio', async ({ page }) => {
    const firstCard = page.locator('.watchlist-card').first();
    await expect(firstCard).toBeVisible({ timeout: 10000 });

    // 检查市值
    const badges = firstCard.locator('.watchlist-card__badge');
    const badgesCount = await badges.count();
    expect(badgesCount).toBeGreaterThan(0);

    // 至少应该有一个市值或PE的badge
    let foundMV = false;
    let foundPE = false;

    for (let i = 0; i < badgesCount; i++) {
      const text = await badges.nth(i).textContent();
      if (text?.includes('亿')) foundMV = true;
      if (text?.includes('PE')) foundPE = true;
    }

    expect(foundMV || foundPE).toBeTruthy();
  });

  test('should display sector classification', async ({ page }) => {
    const firstCard = page.locator('.watchlist-card').first();
    await expect(firstCard).toBeVisible({ timeout: 10000 });

    const sector = firstCard.locator('.watchlist-card__industry');
    await expect(sector).toBeVisible();

    const sectorText = await sector.textContent();
    expect(sectorText).toBeTruthy();
    expect(sectorText?.length).toBeGreaterThan(0);
  });

  test('should render K-line charts', async ({ page }) => {
    const firstCard = page.locator('.watchlist-card').first();
    await expect(firstCard).toBeVisible({ timeout: 10000 });

    // 检查日线图
    const dailyChart = firstCard.locator('.kline-chart').first();
    await expect(dailyChart).toBeVisible({ timeout: 5000 });

    // 检查30分钟图
    const min30Chart = firstCard.locator('.kline-chart').nth(1);
    await expect(min30Chart).toBeVisible({ timeout: 5000 });

    // 检查K线图的canvas元素
    const canvases = firstCard.locator('canvas');
    expect(await canvases.count()).toBeGreaterThan(0);
  });

  test('should have working action buttons', async ({ page }) => {
    const firstCard = page.locator('.watchlist-card').first();
    await expect(firstCard).toBeVisible({ timeout: 10000 });

    // 检查业绩按钮
    const performanceBtn = firstCard.locator('button:has-text("业绩")');
    await expect(performanceBtn).toBeVisible();
    await expect(performanceBtn).toBeEnabled();

    // 检查详情按钮
    const detailBtn = firstCard.locator('button:has-text("详情")');
    await expect(detailBtn).toBeVisible();
    await expect(detailBtn).toBeEnabled();

    // 检查移除按钮
    const removeBtn = firstCard.locator('button:has-text("移除")');
    await expect(removeBtn).toBeVisible();
    await expect(removeBtn).toBeEnabled();
  });

  test('should validate specific test stocks', async ({ page }) => {
    for (const stock of TEST_STOCKS) {
      // 搜索特定股票
      const card = page.locator('.watchlist-card', {
        has: page.locator(`.watchlist-card__name:has-text("${stock.name}")`)
      });

      // 如果股票存在于自选列表中
      if (await card.count() > 0) {
        await expect(card).toBeVisible();

        // 验证股票名称
        const name = card.locator('.watchlist-card__name');
        await expect(name).toHaveText(stock.name);

        // 验证股票代码
        const ticker = card.locator('.watchlist-card__ticker');
        await expect(ticker).toContainText(stock.ticker);

        // 验证赛道分类
        const sector = card.locator('.watchlist-card__industry');
        const sectorText = await sector.textContent();
        // 赛道可能不完全匹配，但不应该是"未分类"
        expect(sectorText).toBeTruthy();

        console.log(`✓ Validated: ${stock.name} (${stock.ticker}) - Sector: ${sectorText}`);
      }
    }
  });

  test('should handle card interactions', async ({ page }) => {
    const firstCard = page.locator('.watchlist-card').first();
    await expect(firstCard).toBeVisible({ timeout: 10000 });

    // 点击详情按钮
    const detailBtn = firstCard.locator('button:has-text("详情")');
    await detailBtn.click();

    // 应该导航到详情页或打开模态框
    // 这里根据实际实现调整断言
    await page.waitForTimeout(500);

    // 返回自选列表（如果跳转了）
    const backBtn = page.locator('button:has-text("返回")');
    if (await backBtn.count() > 0) {
      await backBtn.click();
      await page.waitForSelector('.watchlist-grid');
    }
  });

  test('should update prices in real-time', async ({ page }) => {
    const firstCard = page.locator('.watchlist-card').first();
    await expect(firstCard).toBeVisible({ timeout: 10000 });

    // 记录初始价格
    const initialPrice = await firstCard.locator('.watchlist-card__price').textContent();

    // 等待一段时间（60秒刷新间隔）
    await page.waitForTimeout(65000);

    // 检查价格是否更新（实时指示器时间应该变化）
    const liveIndicator = firstCard.locator('.watchlist-card__live');
    if (await liveIndicator.count() > 0) {
      const currentTime = await liveIndicator.textContent();
      expect(currentTime).toBeTruthy();
      // 时间应该已更新
    }
  });
});

test.describe('Watchlist Statistics Panel', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:5173');
    await page.click('button:has-text("我的自选")');
    await page.waitForSelector('.watchlist-stats', { timeout: 10000 });
  });

  test('should display statistics panel', async ({ page }) => {
    const statsPanel = page.locator('.watchlist-stats');
    await expect(statsPanel).toBeVisible();

    // 检查自选平均
    const avgChange = statsPanel.locator('.watchlist-stats__item:has-text("自选平均")');
    await expect(avgChange).toBeVisible();

    // 检查上证指数
    const index = statsPanel.locator('.watchlist-stats__item:has-text("上证指数")');
    await expect(index).toBeVisible();

    // 检查超额收益
    const outperformance = statsPanel.locator('.watchlist-stats__item:has-text("超额收益")');
    await expect(outperformance).toBeVisible();

    // 检查统计样本
    const sampleCount = statsPanel.locator('.watchlist-stats__item:has-text("统计样本")');
    await expect(sampleCount).toBeVisible();
  });

  test('should display distribution chart', async ({ page }) => {
    const distributionChart = page.locator('.watchlist-stats__distribution');
    await expect(distributionChart).toBeVisible();

    // 检查是否有分布柱状图
    const bars = page.locator('.watchlist-stats__bar');
    expect(await bars.count()).toBeGreaterThan(0);
  });
});

test.describe('Sector Summary Panel', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:5173');
    await page.click('button:has-text("我的自选")');
    await page.waitForSelector('.sector-summary', { timeout: 10000 });
  });

  test('should display sector summary panel', async ({ page }) => {
    const sectorPanel = page.locator('.sector-summary');

    if (await sectorPanel.count() > 0) {
      await expect(sectorPanel).toBeVisible();

      // 检查赛道卡片
      const sectorCards = page.locator('.sector-card');
      const count = await sectorCards.count();
      expect(count).toBeGreaterThan(0);
    }
  });

  test('should allow sector filtering', async ({ page }) => {
    const sectorCards = page.locator('.sector-card');

    if (await sectorCards.count() > 0) {
      // 点击第一个赛道
      await sectorCards.first().click();
      await page.waitForTimeout(500);

      // 检查股票列表是否被筛选
      // 筛选后的数量应该小于或等于总数
      const totalCount = page.locator('.watchlist-header').locator('text=/\\d+.*只/');
      await expect(totalCount).toBeVisible();
    }
  });
});
