# GitHub Setup & Usage Guide for Beginners

## Table of Contents
1. [What is GitHub?](#what-is-github)
2. [Initial Setup](#initial-setup)
3. [Setting up Your Project](#setting-up-your-project)
4. [Basic Git Commands](#basic-git-commands)
5. [GitHub Workflow](#github-workflow)
6. [Best Practices & Conventions](#best-practices--conventions)
7. [Common Scenarios](#common-scenarios)
8. [Troubleshooting](#troubleshooting)

## What is GitHub?

GitHub is a cloud-based platform that uses Git (version control system) to:
- **Track changes** to your code over time
- **Backup** your code in the cloud
- **Collaborate** with others
- **Share** your projects publicly or privately
- **Manage different versions** of your software

Think of it as "Google Drive for code" but much more powerful.

## Initial Setup

### 1. Install Git
```bash
# Check if Git is already installed
git --version

# If not installed, download from: https://git-scm.com/downloads
```

### 2. Create GitHub Account
- Go to [github.com](https://github.com)
- Sign up for a free account
- Choose a professional username (you'll use this for your portfolio)

### 3. Configure Git Locally
```bash
# Set your name and email (use the same email as your GitHub account)
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# Optional: Set default branch name to 'main'
git config --global init.defaultBranch main
```

### 4. Set up Authentication
**Option A: Personal Access Token (Recommended)**
1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token with `repo` permissions
3. Save the token securely - you'll use it as your password

**Option B: SSH Keys (More Advanced)**
```bash
# Generate SSH key
ssh-keygen -t ed25519 -C "your.email@example.com"

# Add to SSH agent
ssh-add ~/.ssh/id_ed25519

# Copy public key and add to GitHub
cat ~/.ssh/id_ed25519.pub
```

## Setting up Your Project

### 1. Initialize Local Repository
```bash
# Navigate to your project directory
cd /c/Users/Justin/Desktop/NotepadLM_PDFScraper_V1.5

# Initialize Git repository
git init

# Add all files to staging
git add .

# Create first commit
git commit -m "Initial commit: PDF scraper v2.0"
```

### 2. Create GitHub Repository
1. Go to GitHub and click "New repository"
2. Repository name: `NotepadLM-PDFScraper`
3. Description: "PDF and Video Content Scraper for SmartAdvocate knowledge base with OCR and transcription"
4. Choose Public or Private
5. **Don't** initialize with README (since you already have files)
6. Click "Create repository"

### 3. Connect Local to GitHub
```bash
# Add GitHub repository as remote origin
git remote add origin https://github.com/YOUR_USERNAME/NotepadLM-PDFScraper.git

# Push your code to GitHub
git push -u origin main
```

## Basic Git Commands

### Essential Commands
```bash
# Check status of your files
git status

# Add files to staging area
git add filename.py          # Add specific file
git add .                    # Add all files
git add *.py                 # Add all Python files

# Commit changes with a message
git commit -m "Your commit message"

# Push changes to GitHub
git push

# Pull latest changes from GitHub
git pull

# View commit history
git log --oneline

# See what changed in files
git diff
```

### Workflow Commands
```bash
# Create and switch to new branch
git checkout -b feature-branch-name

# Switch between branches
git checkout main
git checkout feature-branch-name

# Merge branch into main
git checkout main
git merge feature-branch-name

# Delete branch after merging
git branch -d feature-branch-name
```

## GitHub Workflow

### Daily Workflow
1. **Start your day**: `git pull` (get latest changes)
2. **Make changes**: Edit your code
3. **Stage changes**: `git add .`
4. **Commit changes**: `git commit -m "Descriptive message"`
5. **Push to GitHub**: `git push`

### Feature Development Workflow
1. **Create branch**: `git checkout -b add-new-feature`
2. **Develop feature**: Make your changes
3. **Commit regularly**: Small, focused commits
4. **Push branch**: `git push -u origin add-new-feature`
5. **Create Pull Request** on GitHub
6. **Merge after review**
7. **Delete branch**: `git branch -d add-new-feature`

## Best Practices & Conventions

### Commit Message Conventions
```bash
# Good commit messages:
git commit -m "Add OCR functionality for PDF processing"
git commit -m "Fix timeout issue in video transcription"
git commit -m "Update requirements.txt with new dependencies"
git commit -m "Refactor: Extract video processing into separate class"

# Bad commit messages:
git commit -m "fix"
git commit -m "changes"
git commit -m "stuff"
```

### Commit Message Format
```
<type>: <description>

Types:
- feat: New feature
- fix: Bug fix
- docs: Documentation changes
- style: Code formatting
- refactor: Code restructuring
- test: Adding tests
- chore: Maintenance tasks
```

### Branch Naming Conventions
```bash
# Feature branches
git checkout -b feature/video-transcription
git checkout -b feature/improved-ocr

# Bug fix branches
git checkout -b fix/timeout-error
git checkout -b fix/pdf-corruption

# Documentation branches
git checkout -b docs/setup-guide
```

### .gitignore Best Practices
Your project should have a `.gitignore` file to exclude:
```gitignore
# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
env/
.venv/
.env

# Project specific
/logs/
/data/
/PDFs/
*.log
temp_*.pdf

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
```

## Common Scenarios

### Scenario 1: You Made Changes and Want to Save Them
```bash
git add .
git commit -m "Implement new PDF categorization logic"
git push
```

### Scenario 2: You Want to Work on a New Feature
```bash
git checkout -b feature/docker-support
# Make your changes
git add .
git commit -m "Add Docker configuration files"
git push -u origin feature/docker-support
# Create Pull Request on GitHub
```

### Scenario 3: You Made a Mistake in Your Last Commit
```bash
# If you haven't pushed yet
git reset --soft HEAD~1  # Undo commit but keep changes
git commit -m "Corrected commit message"

# If you already pushed (avoid if working with others)
git push --force
```

### Scenario 4: You Want to See What Changed
```bash
git status                    # See modified files
git diff                      # See specific changes
git log --oneline -10         # See last 10 commits
```

## Troubleshooting

### Common Issues

**Problem**: "Permission denied" when pushing
**Solution**: Check your authentication (token/SSH key)

**Problem**: "Repository not found"
**Solution**: Verify remote URL: `git remote -v`

**Problem**: Merge conflicts
**Solution**: 
```bash
git status  # See conflicted files
# Edit files to resolve conflicts
git add .
git commit -m "Resolve merge conflicts"
```

**Problem**: Accidentally committed large files
**Solution**:
```bash
git reset --soft HEAD~1
# Add large files to .gitignore
git add .gitignore
git commit -m "Add .gitignore for large files"
```

### Useful Commands for Recovery
```bash
# See all commits
git reflog

# Undo last commit (keep changes)
git reset --soft HEAD~1

# Undo last commit (discard changes)
git reset --hard HEAD~1

# Create backup branch before risky operations
git checkout -b backup-branch
```

## Next Steps for Your Project

1. **Create .gitignore** (see template above)
2. **Initialize repository** with your current code
3. **Create first release** tag: `git tag -a v2.0 -m "Version 2.0"`
4. **Set up Issues** on GitHub for tracking improvements
5. **Create documentation** in README.md
6. **Consider CI/CD** with GitHub Actions later

## Resources

- [GitHub Documentation](https://docs.github.com)
- [Git Cheat Sheet](https://education.github.com/git-cheat-sheet-education.pdf)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [GitHub Flow](https://guides.github.com/introduction/flow/)

Remember: **Commit early, commit often!** It's better to have many small commits than one large one. 