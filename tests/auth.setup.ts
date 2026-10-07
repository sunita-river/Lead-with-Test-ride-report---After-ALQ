import { test as setup } from '@playwright/test';
import { credentials } from '../credentials/credentials';
import { LoginPage } from '../pages/LoginPage';

const authFile = 'playwright/.auth/user.json';

setup('authenticate', async ({ page }) => {
  const login = new LoginPage(page);
  await login.login(credentials.baseUrl, credentials.username, credentials.password);

  await page.context().storageState({ path: authFile });
});
