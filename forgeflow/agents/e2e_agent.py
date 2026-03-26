#!/usr/bin/env python3
"""
E2E Testing Agent - End-to-End Testing Setup Generation
Generates Playwright, Cypress configurations, test templates, CI integration

Part of the specialized agent architecture:
- forgeflow e2e <path> → e2e_mcp → E2ETestingAgent
"""
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from .base_agent import BaseAgent


# =============================================================================
# PLAYWRIGHT CONFIGURATION
# =============================================================================

PLAYWRIGHT_CONFIG = '''import {{ defineConfig, devices }} from '@playwright/test';

/**
 * ForgeFlow Generated Playwright Configuration
 * @see https://playwright.dev/docs/test-configuration
 */
export default defineConfig({{
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['html', {{ open: 'never' }}],
    ['junit', {{ outputFile: 'test-results/junit.xml' }}],
    ['json', {{ outputFile: 'test-results/results.json' }}],
  ],
  
  use: {{
    baseURL: process.env.BASE_URL || 'http://localhost:{port}',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  }},

  projects: [
    {{
      name: 'chromium',
      use: {{ ...devices['Desktop Chrome'] }},
    }},
    {{
      name: 'firefox',
      use: {{ ...devices['Desktop Firefox'] }},
    }},
    {{
      name: 'webkit',
      use: {{ ...devices['Desktop Safari'] }},
    }},
    {{
      name: 'Mobile Chrome',
      use: {{ ...devices['Pixel 5'] }},
    }},
    {{
      name: 'Mobile Safari',
      use: {{ ...devices['iPhone 12'] }},
    }},
  ],

  webServer: {{
    command: '{start_command}',
    url: 'http://localhost:{port}',
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
  }},
}});
'''

PLAYWRIGHT_PACKAGE_JSON_SCRIPTS = '''
  "test:e2e": "playwright test",
  "test:e2e:ui": "playwright test --ui",
  "test:e2e:headed": "playwright test --headed",
  "test:e2e:debug": "playwright test --debug",
  "test:e2e:report": "playwright show-report",
  "test:e2e:codegen": "playwright codegen"
'''

# =============================================================================
# PLAYWRIGHT TEST TEMPLATES
# =============================================================================

PLAYWRIGHT_TEST_AUTH = '''import { test, expect } from '@playwright/test';

/**
 * ForgeFlow Generated Authentication Tests
 */

test.describe('Authentication', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display login form', async ({ page }) => {
    await page.goto('/login');
    
    await expect(page.locator('input[name="email"]')).toBeVisible();
    await expect(page.locator('input[name="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('should show error for invalid credentials', async ({ page }) => {
    await page.goto('/login');
    
    await page.fill('input[name="email"]', 'invalid@example.com');
    await page.fill('input[name="password"]', 'wrongpassword');
    await page.click('button[type="submit"]');
    
    await expect(page.locator('[data-testid="error-message"]')).toBeVisible();
  });

  test('should login successfully with valid credentials', async ({ page }) => {
    await page.goto('/login');
    
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'validpassword');
    await page.click('button[type="submit"]');
    
    // Should redirect to dashboard
    await expect(page).toHaveURL(/.*dashboard/);
    await expect(page.locator('[data-testid="user-menu"]')).toBeVisible();
  });

  test('should logout successfully', async ({ page }) => {
    // First login
    await page.goto('/login');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'validpassword');
    await page.click('button[type="submit"]');
    
    // Then logout
    await page.click('[data-testid="user-menu"]');
    await page.click('[data-testid="logout-button"]');
    
    // Should redirect to login
    await expect(page).toHaveURL(/.*login/);
  });
});
'''

PLAYWRIGHT_TEST_NAVIGATION = '''import { test, expect } from '@playwright/test';

/**
 * ForgeFlow Generated Navigation Tests
 */

test.describe('Navigation', () => {
  test('should navigate to home page', async ({ page }) => {
    await page.goto('/');
    
    await expect(page).toHaveTitle(/.*/);
    await expect(page.locator('nav')).toBeVisible();
  });

  test('should have working navigation links', async ({ page }) => {
    await page.goto('/');
    
    // Check main navigation links
    const navLinks = page.locator('nav a');
    const count = await navLinks.count();
    
    expect(count).toBeGreaterThan(0);
    
    // Click first link and verify navigation
    const firstLink = navLinks.first();
    const href = await firstLink.getAttribute('href');
    
    if (href && !href.startsWith('http')) {
      await firstLink.click();
      await expect(page).toHaveURL(new RegExp(href.replace(/\\//g, '\\\\/')));
    }
  });

  test('should display 404 page for invalid routes', async ({ page }) => {
    await page.goto('/this-page-does-not-exist-12345');
    
    await expect(page.locator('text=/404|not found/i')).toBeVisible();
  });

  test('should have working breadcrumbs', async ({ page }) => {
    await page.goto('/dashboard/settings');
    
    const breadcrumbs = page.locator('[data-testid="breadcrumbs"]');
    
    if (await breadcrumbs.isVisible()) {
      await expect(breadcrumbs.locator('a')).toHaveCount(await breadcrumbs.locator('a').count());
    }
  });

  test('should be responsive', async ({ page }) => {
    // Test mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');
    
    // Mobile menu should be visible
    const mobileMenu = page.locator('[data-testid="mobile-menu-button"]');
    
    if (await mobileMenu.isVisible()) {
      await mobileMenu.click();
      await expect(page.locator('[data-testid="mobile-nav"]')).toBeVisible();
    }
  });
});
'''

PLAYWRIGHT_TEST_FORMS = '''import { test, expect } from '@playwright/test';

/**
 * ForgeFlow Generated Form Tests
 */

test.describe('Forms', () => {
  test.describe('Contact Form', () => {
    test('should display contact form', async ({ page }) => {
      await page.goto('/contact');
      
      await expect(page.locator('form')).toBeVisible();
      await expect(page.locator('input[name="name"]')).toBeVisible();
      await expect(page.locator('input[name="email"]')).toBeVisible();
      await expect(page.locator('textarea[name="message"]')).toBeVisible();
    });

    test('should validate required fields', async ({ page }) => {
      await page.goto('/contact');
      
      await page.click('button[type="submit"]');
      
      // Check for validation errors
      await expect(page.locator('[data-testid="error"]').first()).toBeVisible();
    });

    test('should validate email format', async ({ page }) => {
      await page.goto('/contact');
      
      await page.fill('input[name="email"]', 'invalid-email');
      await page.click('button[type="submit"]');
      
      await expect(page.locator('text=/invalid.*email/i')).toBeVisible();
    });

    test('should submit form successfully', async ({ page }) => {
      await page.goto('/contact');
      
      await page.fill('input[name="name"]', 'Test User');
      await page.fill('input[name="email"]', 'test@example.com');
      await page.fill('textarea[name="message"]', 'This is a test message');
      
      await page.click('button[type="submit"]');
      
      // Should show success message
      await expect(page.locator('text=/success|thank you/i')).toBeVisible();
    });
  });

  test.describe('Search Form', () => {
    test('should perform search', async ({ page }) => {
      await page.goto('/');
      
      const searchInput = page.locator('input[type="search"], input[name="search"], input[placeholder*="search" i]');
      
      if (await searchInput.isVisible()) {
        await searchInput.fill('test query');
        await searchInput.press('Enter');
        
        // Should navigate to search results or show results
        await expect(page.locator('text=/result|found|search/i')).toBeVisible();
      }
    });
  });
});
'''

PLAYWRIGHT_TEST_API = '''import {{ test, expect }} from '@playwright/test';

/**
 * ForgeFlow Generated API Tests
 */

test.describe('API Endpoints', () => {{
  const baseURL = process.env.API_URL || 'http://localhost:{port}/api';

  test('should return health check', async ({{ request }}) => {{
    const response = await request.get(`${{baseURL}}/health`);
    
    expect(response.ok()).toBeTruthy();
    
    const body = await response.json();
    expect(body.status).toBe('ok');
  }});

  test('should return 401 for protected endpoints without auth', async ({{ request }}) => {{
    const response = await request.get(`${{baseURL}}/protected`);
    
    expect(response.status()).toBe(401);
  }});

  test('should handle CORS correctly', async ({{ request }}) => {{
    const response = await request.get(`${{baseURL}}/health`, {{
      headers: {{
        'Origin': 'http://localhost:3000',
      }},
    }});
    
    expect(response.ok()).toBeTruthy();
  }});

  test('should validate request body', async ({{ request }}) => {{
    const response = await request.post(`${{baseURL}}/users`, {{
      data: {{
        // Missing required fields
      }},
    }});
    
    expect(response.status()).toBe(400);
  }});
}});
'''

PLAYWRIGHT_FIXTURES = '''import { test as base, expect } from '@playwright/test';

/**
 * ForgeFlow Generated Test Fixtures
 */

// Extend base test with custom fixtures
export const test = base.extend<{
  authenticatedPage: Page;
}>({
  authenticatedPage: async ({ page }, use) => {
    // Setup: Login before test
    await page.goto('/login');
    await page.fill('input[name="email"]', process.env.TEST_USER_EMAIL || 'test@example.com');
    await page.fill('input[name="password"]', process.env.TEST_USER_PASSWORD || 'testpassword');
    await page.click('button[type="submit"]');
    
    // Wait for authentication to complete
    await page.waitForURL(/.*dashboard/);
    
    // Use the authenticated page
    await use(page);
    
    // Teardown: Logout after test
    await page.click('[data-testid="user-menu"]');
    await page.click('[data-testid="logout-button"]');
  },
});

export { expect };
'''

PLAYWRIGHT_GLOBAL_SETUP = '''import { chromium, FullConfig } from '@playwright/test';

/**
 * ForgeFlow Generated Global Setup
 * Runs once before all tests
 */
async function globalSetup(config: FullConfig) {
  console.log('🎭 Running global setup...');
  
  // Create browser for setup tasks
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  try {
    // Verify the application is running
    await page.goto(config.projects[0].use.baseURL || 'http://localhost:3000');
    console.log('✅ Application is running');
  } catch (error) {
    console.error('❌ Application is not running');
    throw error;
  } finally {
    await browser.close();
  }
}

export default globalSetup;
'''


# =============================================================================
# CYPRESS CONFIGURATION
# =============================================================================

CYPRESS_CONFIG = '''import {{ defineConfig }} from 'cypress';

/**
 * ForgeFlow Generated Cypress Configuration
 */
export default defineConfig({{
  e2e: {{
    baseUrl: process.env.CYPRESS_BASE_URL || 'http://localhost:{port}',
    supportFile: 'cypress/support/e2e.ts',
    specPattern: 'cypress/e2e/**/*.cy.ts',
    viewportWidth: 1280,
    viewportHeight: 720,
    video: true,
    screenshotOnRunFailure: true,
    retries: {{
      runMode: 2,
      openMode: 0,
    }},
    env: {{
      apiUrl: 'http://localhost:{port}/api',
    }},
    setupNodeEvents(on, config) {{
      // implement node event listeners here
      on('task', {{
        log(message) {{
          console.log(message);
          return null;
        }},
      }});
    }},
  }},
  component: {{
    devServer: {{
      framework: 'react',
      bundler: 'vite',
    }},
  }},
}});
'''

CYPRESS_SUPPORT_E2E = '''// ***********************************************************
// ForgeFlow Generated Cypress Support File
// ***********************************************************

import './commands';

// Prevent TypeScript errors for custom commands
declare global {
  namespace Cypress {
    interface Chainable {
      login(email: string, password: string): Chainable<void>;
      logout(): Chainable<void>;
      apiRequest(method: string, url: string, body?: object): Chainable<Response<any>>;
    }
  }
}

// Hide fetch/XHR requests from command log
const app = window.top;
if (app && !app.document.head.querySelector('[data-hide-command-log-request]')) {
  const style = app.document.createElement('style');
  style.innerHTML = '.command-name-request, .command-name-xhr { display: none }';
  style.setAttribute('data-hide-command-log-request', '');
  app.document.head.appendChild(style);
}
'''

CYPRESS_COMMANDS = '''// ***********************************************
// ForgeFlow Generated Custom Commands
// ***********************************************

Cypress.Commands.add('login', (email: string, password: string) => {
  cy.session([email, password], () => {
    cy.visit('/login');
    cy.get('input[name="email"]').type(email);
    cy.get('input[name="password"]').type(password);
    cy.get('button[type="submit"]').click();
    cy.url().should('include', '/dashboard');
  });
});

Cypress.Commands.add('logout', () => {
  cy.get('[data-testid="user-menu"]').click();
  cy.get('[data-testid="logout-button"]').click();
  cy.url().should('include', '/login');
});

Cypress.Commands.add('apiRequest', (method: string, url: string, body?: object) => {
  return cy.request({
    method,
    url: `${Cypress.env('apiUrl')}${url}`,
    body,
    failOnStatusCode: false,
  });
});
'''

CYPRESS_TEST_AUTH = '''/// <reference types="cypress" />

/**
 * ForgeFlow Generated Authentication Tests
 */

describe('Authentication', () => {
  beforeEach(() => {
    cy.visit('/');
  });

  it('should display login form', () => {
    cy.visit('/login');
    
    cy.get('input[name="email"]').should('be.visible');
    cy.get('input[name="password"]').should('be.visible');
    cy.get('button[type="submit"]').should('be.visible');
  });

  it('should show error for invalid credentials', () => {
    cy.visit('/login');
    
    cy.get('input[name="email"]').type('invalid@example.com');
    cy.get('input[name="password"]').type('wrongpassword');
    cy.get('button[type="submit"]').click();
    
    cy.get('[data-testid="error-message"]').should('be.visible');
  });

  it('should login successfully with valid credentials', () => {
    cy.login('test@example.com', 'validpassword');
    
    cy.url().should('include', '/dashboard');
    cy.get('[data-testid="user-menu"]').should('be.visible');
  });

  it('should logout successfully', () => {
    cy.login('test@example.com', 'validpassword');
    cy.logout();
    
    cy.url().should('include', '/login');
  });
});
'''

CYPRESS_TEST_NAVIGATION = '''/// <reference types="cypress" />

/**
 * ForgeFlow Generated Navigation Tests
 */

describe('Navigation', () => {
  it('should navigate to home page', () => {
    cy.visit('/');
    
    cy.title().should('not.be.empty');
    cy.get('nav').should('be.visible');
  });

  it('should have working navigation links', () => {
    cy.visit('/');
    
    cy.get('nav a').should('have.length.greaterThan', 0);
    
    cy.get('nav a').first().then(($link) => {
      const href = $link.attr('href');
      if (href && !href.startsWith('http')) {
        cy.wrap($link).click();
        cy.url().should('include', href);
      }
    });
  });

  it('should display 404 page for invalid routes', () => {
    cy.visit('/this-page-does-not-exist-12345', { failOnStatusCode: false });
    
    cy.contains(/404|not found/i).should('be.visible');
  });

  it('should be responsive', () => {
    cy.viewport('iphone-x');
    cy.visit('/');
    
    cy.get('[data-testid="mobile-menu-button"]').then(($btn) => {
      if ($btn.is(':visible')) {
        cy.wrap($btn).click();
        cy.get('[data-testid="mobile-nav"]').should('be.visible');
      }
    });
  });
});
'''


# =============================================================================
# CI INTEGRATION FOR E2E
# =============================================================================

E2E_WORKFLOW_PLAYWRIGHT = '''# =============================================================================
# ForgeFlow Generated E2E Tests Workflow (Playwright)
# =============================================================================
name: E2E Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 0 * * *'  # Daily at midnight

jobs:
  e2e-tests:
    name: 🎭 Playwright E2E Tests
    runs-on: ubuntu-latest
    timeout-minutes: 60
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Install Playwright Browsers
        run: npx playwright install --with-deps

      - name: Build application
        run: npm run build

      - name: Run Playwright tests
        run: npx playwright test
        env:
          CI: true
          BASE_URL: http://localhost:{port}

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: playwright-report/
          retention-days: 30

      - name: Upload test artifacts
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: test-artifacts
          path: test-results/
          retention-days: 7
'''

E2E_WORKFLOW_CYPRESS = '''# =============================================================================
# ForgeFlow Generated E2E Tests Workflow (Cypress)
# =============================================================================
name: E2E Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  e2e-tests:
    name: 🌲 Cypress E2E Tests
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Build application
        run: npm run build

      - name: Cypress run
        uses: cypress-io/github-action@v6
        with:
          start: npm run start
          wait-on: 'http://localhost:{port}'
          wait-on-timeout: 120
          browser: chrome

      - name: Upload screenshots
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: cypress-screenshots
          path: cypress/screenshots
          retention-days: 7

      - name: Upload videos
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: cypress-videos
          path: cypress/videos
          retention-days: 7
'''


# =============================================================================
# TEST REPORTING
# =============================================================================

PLAYWRIGHT_REPORTER_CONFIG = '''# ForgeFlow Generated Allure Reporter Config
# Install: npm install -D allure-playwright

# In playwright.config.ts, add to reporter array:
# ['allure-playwright', { outputFolder: 'allure-results' }]

# Generate report:
# npx allure generate allure-results -o allure-report --clean
# npx allure open allure-report
'''


class E2ETestingAgent(BaseAgent):
    """
    End-to-End Testing Agent - Generates E2E test configurations and templates.
    
    Responsibilities:
    - Playwright setup and configuration
    - Cypress setup (alternative)
    - Test templates (login, navigation, forms)
    - CI integration for E2E tests
    - Test reporting setup
    """
    
    def __init__(self):
        super().__init__(
            name="E2ETestingAgent",
            description="Generates End-to-End testing configurations (Playwright, Cypress)"
        )
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate E2E testing configurations based on repository analysis."""
        # Handle params defensively
        if params is None:
            params = {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except:
                params = {"repo_path": params}
        
        repo_path = Path(params.get("repo_path", params.get("path", "."))).resolve()
        overwrite = params.get("greenfield", False)
        framework = params.get("framework", "playwright").lower()
        include_ci = params.get("include_ci", True)
        
        self.log(f"Generating E2E configs for: {repo_path}")
        
        actions = []
        findings = []
        
        # Detect app settings
        app_name = self._detect_app_name(repo_path)
        primary_lang = self._detect_primary_language(repo_path)
        port = "3000" if primary_lang in ["JavaScript", "TypeScript"] else "8000"
        start_command = self._detect_start_command(repo_path)
        
        self.log(f"Detected app: {app_name}, port: {port}, framework: {framework}")
        
        # Generate based on selected framework
        if framework == "playwright":
            e2e_actions = self._generate_playwright(repo_path, port, start_command, overwrite)
            actions.extend(e2e_actions)
        elif framework == "cypress":
            e2e_actions = self._generate_cypress(repo_path, port, overwrite)
            actions.extend(e2e_actions)
        else:
            # Generate both
            actions.extend(self._generate_playwright(repo_path, port, start_command, overwrite))
            actions.extend(self._generate_cypress(repo_path, port, overwrite))

        # Generate CI workflow
        if include_ci:
            ci_actions = self._generate_ci_workflow(repo_path, framework, port, overwrite)
            actions.extend(ci_actions)
        
        return self.create_result(
            status="success",
            summary=f"Generated E2E testing setup for {app_name}",
            data={
                "app_name": app_name,
                "framework": framework,
                "port": port,
                "files_generated": len(actions),
            },
            findings=findings,
            actions=actions
        )
    
    def _detect_app_name(self, repo_path: Path) -> str:
        """Detect application name."""
        package_json = repo_path / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text())
                if isinstance(data, dict) and data.get("name"):
                    return data["name"].replace("@", "").replace("/", "-")
            except:
                pass
        return repo_path.name.lower().replace(" ", "-").replace("_", "-")
    
    def _detect_primary_language(self, repo_path: Path) -> str:
        """Detect primary programming language."""
        ext_counts = {}
        for ext, lang in {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".go": "Go"}.items():
            count = len(list(repo_path.rglob(f"*{ext}")))
            if count > 0:
                ext_counts[lang] = count
        return max(ext_counts, key=ext_counts.get) if ext_counts else "Python"
    
    def _detect_start_command(self, repo_path: Path) -> str:
        """Detect the start command for the application."""
        package_json = repo_path / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text())
                scripts = data.get("scripts", {})
                if "dev" in scripts:
                    return "npm run dev"
                if "start" in scripts:
                    return "npm run start"
            except:
                pass
        
        # Python defaults
        if (repo_path / "manage.py").exists():
            return "python manage.py runserver"
        if (repo_path / "main.py").exists():
            return "python main.py"
        
        return "npm run dev"
    
    def _generate_playwright(self, repo_path: Path, port: str, start_command: str, overwrite: bool = False) -> List[Dict]:
        """Generate Playwright configuration and test files."""
        actions = []
        
        # playwright.config.ts
        config_content = PLAYWRIGHT_CONFIG.format(port=port, start_command=start_command)
        actions.append(self._safe_write(repo_path / "playwright.config.ts", config_content, overwrite))

        # Create tests/e2e directory
        tests_path = repo_path / "tests" / "e2e"
        tests_path.mkdir(parents=True, exist_ok=True)

        # Test files
        actions.append(self._safe_write(tests_path / "auth.spec.ts", PLAYWRIGHT_TEST_AUTH, overwrite))

        actions.append(self._safe_write(tests_path / "navigation.spec.ts", PLAYWRIGHT_TEST_NAVIGATION, overwrite))

        actions.append(self._safe_write(tests_path / "forms.spec.ts", PLAYWRIGHT_TEST_FORMS, overwrite))

        api_content = PLAYWRIGHT_TEST_API.format(port=port)
        actions.append(self._safe_write(tests_path / "api.spec.ts", api_content, overwrite))

        # Fixtures
        fixtures_path = tests_path / "fixtures"
        fixtures_path.mkdir(exist_ok=True)
        actions.append(self._safe_write(fixtures_path / "test-fixtures.ts", PLAYWRIGHT_FIXTURES, overwrite))

        # Global setup
        actions.append(self._safe_write(tests_path / "global-setup.ts", PLAYWRIGHT_GLOBAL_SETUP, overwrite))
        
        return actions
    
    def _generate_cypress(self, repo_path: Path, port: str, overwrite: bool = False) -> List[Dict]:
        """Generate Cypress configuration and test files."""
        actions = []
        
        # cypress.config.ts
        config_content = CYPRESS_CONFIG.format(port=port)
        actions.append(self._safe_write(repo_path / "cypress.config.ts", config_content, overwrite))

        # Create cypress directory structure
        cypress_path = repo_path / "cypress"
        e2e_path = cypress_path / "e2e"
        support_path = cypress_path / "support"

        e2e_path.mkdir(parents=True, exist_ok=True)
        support_path.mkdir(parents=True, exist_ok=True)

        # Support files
        actions.append(self._safe_write(support_path / "e2e.ts", CYPRESS_SUPPORT_E2E, overwrite))

        actions.append(self._safe_write(support_path / "commands.ts", CYPRESS_COMMANDS, overwrite))

        # Test files
        actions.append(self._safe_write(e2e_path / "auth.cy.ts", CYPRESS_TEST_AUTH, overwrite))

        actions.append(self._safe_write(e2e_path / "navigation.cy.ts", CYPRESS_TEST_NAVIGATION, overwrite))
        
        return actions
    
    def _generate_ci_workflow(self, repo_path: Path, framework: str, port: str, overwrite: bool = False) -> List[Dict]:
        """Generate CI workflow for E2E tests."""
        actions = []
        
        workflows_path = repo_path / ".github" / "workflows"
        workflows_path.mkdir(parents=True, exist_ok=True)
        
        if framework == "playwright":
            workflow_content = E2E_WORKFLOW_PLAYWRIGHT.format(port=port)
        else:
            workflow_content = E2E_WORKFLOW_CYPRESS.format(port=port)

        actions.append(self._safe_write(workflows_path / "e2e.yml", workflow_content, overwrite))
        
        return actions
