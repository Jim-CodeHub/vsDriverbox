// DemoDlg.cpp : 实现文件
//

#include "stdafx.h"
#include "Demo.h"
#include "DemoDlg.h"
#include "afxdialogex.h"
#include "IHsAutoPrintPort_Rip.h"

#ifdef _DEBUG
#define new DEBUG_NEW
#endif

#define THREAD_SEND_RPN_TASK		1

// 用于应用程序“关于”菜单项的 CAboutDlg 对话框
class CAboutDlg : public CDialogEx
{
public:
	CAboutDlg();

// 对话框数据
	enum { IDD = IDD_ABOUTBOX };

	protected:
	virtual void DoDataExchange(CDataExchange* pDX);    // DDX/DDV 支持

// 实现
protected:
	DECLARE_MESSAGE_MAP()
};

CAboutDlg::CAboutDlg() : CDialogEx(CAboutDlg::IDD)
{
}

void CAboutDlg::DoDataExchange(CDataExchange* pDX)
{
	CDialogEx::DoDataExchange(pDX);
}

BEGIN_MESSAGE_MAP(CAboutDlg, CDialogEx)
END_MESSAGE_MAP()

// CDemoDlg 对话框
CDemoDlg::CDemoDlg(CWnd* pParent /*=NULL*/)
	: CDialogEx(CDemoDlg::IDD, pParent)
	, m_strProgress(_T(""))
{
	m_hIcon		 = AfxGetApp()->LoadIcon(IDR_MAINFRAME);
	m_szFilename = theApp.GetProfileString(_T("HsRipMemMap-Demo"), _T("FILE"), _T(""));
	m_dbProgress = 0;
}

void CDemoDlg::DoDataExchange(CDataExchange* pDX)
{
	CDialogEx::DoDataExchange(pDX);
	DDX_Text(pDX, IDC_EDIT_PRN_PATH, m_szFilename);
	DDX_Text(pDX, IDC_STATIC_PROGRESS, m_strProgress);
}

BEGIN_MESSAGE_MAP(CDemoDlg, CDialogEx)
	ON_WM_SYSCOMMAND()
	ON_WM_PAINT()
	ON_WM_TIMER()
	ON_WM_QUERYDRAGICON()
	ON_BN_CLICKED(IDCANCEL, &CDemoDlg::OnBnClickedCancel)
	ON_BN_CLICKED(IDC_BTN_CLOSE, &CDemoDlg::OnBnClickedBtnClose)
	ON_BN_CLICKED(IDC_BTN_START, &CDemoDlg::OnBnClickedBtnStart)
	ON_BN_CLICKED(IDC_BTN_OPEN_PRN, &CDemoDlg::OnBnClickedBtnOpenPrn)
	ON_BN_CLICKED(IDC_BTN_START_MM, &CDemoDlg::OnBnClickedBtnStartMm)
	ON_BN_CLICKED(IDC_BTN_CLOSE_MM, &CDemoDlg::OnBnClickedBtnCloseMm)
END_MESSAGE_MAP()

// CDemoDlg 消息处理程序

BOOL CDemoDlg::OnInitDialog()
{
	CDialogEx::OnInitDialog();

	// 将“关于...”菜单项添加到系统菜单中。

	// IDM_ABOUTBOX 必须在系统命令范围内。
	ASSERT((IDM_ABOUTBOX & 0xFFF0) == IDM_ABOUTBOX);
	ASSERT(IDM_ABOUTBOX < 0xF000);

	CMenu* pSysMenu = GetSystemMenu(FALSE);
	if (pSysMenu != NULL)
	{
		BOOL bNameValid;
		CString strAboutMenu;
		bNameValid = strAboutMenu.LoadString(IDS_ABOUTBOX);
		ASSERT(bNameValid);
		if (!strAboutMenu.IsEmpty())
		{
			pSysMenu->AppendMenu(MF_SEPARATOR);
			pSysMenu->AppendMenu(MF_STRING, IDM_ABOUTBOX, strAboutMenu);
		}
	}

	// 设置此对话框的图标。当应用程序主窗口不是对话框时，框架将自动
	//  执行此操作
	SetIcon(m_hIcon, TRUE);			// 设置大图标
	SetIcon(m_hIcon, FALSE);		// 设置小图标

	// TODO: 在此添加额外的初始化代码
	SetTimer(0, 500, NULL);

	return TRUE;  // 除非将焦点设置到控件，否则返回 TRUE
}

void CDemoDlg::OnSysCommand(UINT nID, LPARAM lParam)
{
	if ((nID & 0xFFF0) == IDM_ABOUTBOX)
	{
		CAboutDlg dlgAbout;
		dlgAbout.DoModal();
	}
	else
	{
		CDialogEx::OnSysCommand(nID, lParam);
	}
}

// 如果向对话框添加最小化按钮，则需要下面的代码
//  来绘制该图标。对于使用文档/视图模型的 MFC 应用程序，
//  这将由框架自动完成。

void CDemoDlg::OnPaint()
{
	if (IsIconic())
	{
		CPaintDC dc(this); // 用于绘制的设备上下文

		SendMessage(WM_ICONERASEBKGND, reinterpret_cast<WPARAM>(dc.GetSafeHdc()), 0);

		// 使图标在工作区矩形中居中
		int cxIcon = GetSystemMetrics(SM_CXICON);
		int cyIcon = GetSystemMetrics(SM_CYICON);
		CRect rect;
		GetClientRect(&rect);
		int x = (rect.Width() - cxIcon + 1) / 2;
		int y = (rect.Height() - cyIcon + 1) / 2;

		// 绘制图标
		dc.DrawIcon(x, y, m_hIcon);
	}
	else
	{
		CDialogEx::OnPaint();
	}
}

void CDemoDlg::OnTimer(UINT_PTR nIDEvent)
{
	if (0 == nIDEvent)
	{
		m_strProgress.Format(_T("%.2f"), m_dbProgress);
		UpdateData(FALSE);
	}
	CDialogEx::OnTimer(nIDEvent);
}

//当用户拖动最小化窗口时系统调用此函数取得光标
//显示。
HCURSOR CDemoDlg::OnQueryDragIcon()
{
	return static_cast<HCURSOR>(m_hIcon);
}

void CDemoDlg::OnBnClickedCancel()
{
	CDialogEx::OnCancel();
}

BOOL CDemoDlg::ReadPrnDataSendToMemMap()
{
#define  SEND_SIZE_ONCE			(8*1024*1024)

	BOOL			bRet			= TRUE;
	unsigned char*	pBuffer			= nullptr;
	HANDLE			hFile			= NULL;
	INT64			i64FileSize		= 0;
	INT				nSendSizeOnce	= SEND_SIZE_ONCE;
	INT				nRet			= HPE_SUCEES;

	hFile = CreateFile(
		m_szFilename,				 // 文件名路径
		GENERIC_READ,                // 访问模式只读
		FILE_SHARE_READ,             // 共享模式允许其他进程同时读取
		NULL,                        // 安全属性
		OPEN_EXISTING,               // 模式：文件必须存在否则打开失败
		FILE_ATTRIBUTE_NORMAL,       // 文件属性
		NULL                         // 模板文件句柄
	);

	if (hFile == INVALID_HANDLE_VALUE) 
	{
		return FALSE;
	}

	// 获取文件大小
	DWORD	dwFileSizeH = 0;
	DWORD	dwFileSizeL = 0;
		
	dwFileSizeL = GetFileSize(hFile, &dwFileSizeH);
	i64FileSize = ((INT64)dwFileSizeH << 32) | dwFileSizeL;

	// 启动RIP发送任务
	while (1)
	{
		nRet = StartSendRipTask_Rip();
		if (HPE_SUCEES == nRet)
		{
			break;
		}
		else
		{
			StopSendRipTask_Rip();
		}
		Sleep(1000);
	}

	pBuffer = new unsigned char[SEND_SIZE_ONCE];

	DWORD	dwReadSize			= 0;
	INT64	i64RemainDataSize	= 0;
	INT64   i64AllReadData		= 0;
	INT		nCount				= 0;

	while (i64AllReadData < i64FileSize)
	{
		i64RemainDataSize = i64FileSize - i64AllReadData;
		if (i64RemainDataSize > SEND_SIZE_ONCE)
		{
			nSendSizeOnce = SEND_SIZE_ONCE;
		}
		else
		{
			nSendSizeOnce = i64RemainDataSize;
		}

		if (!IsCanSendData(nSendSizeOnce))
		{
			// 缓冲区满，等待一段时间再发送
			Sleep(100);
			continue;
		}		
		
		if (!ReadFile(hFile, pBuffer, nSendSizeOnce, &dwReadSize, NULL))
		{
			bRet = FALSE;
			break;
		}

		if (nSendSizeOnce != dwReadSize)
		{
			bRet = FALSE;
			break;
		}

		i64AllReadData += (INT64)dwReadSize;
		nCount++;

		int nRet = SendDataAutoPrintPort_Rip(pBuffer, nSendSizeOnce);
		if (HPE_SUCEES != nRet)
		{
			bRet = FALSE;
			break;
		}

		INT64 nAllWritePos = GetMemMapAllWriteSize();
		if (nAllWritePos != i64AllReadData)
		{
			bRet = FALSE;
		}

		m_dbProgress	 = i64AllReadData*1.0/i64FileSize;
	}

	if (bRet)
	{
		nRet = FinishSendRipTask_Rip();
	}
	else
	{
		nRet = StopSendRipTask_Rip();
	}
	
	CloseHandle(hFile);

	if (pBuffer)
	{
		delete[] pBuffer; pBuffer = nullptr;
	}

	return bRet;
}

int CDemoDlg::ThreadRun(int nThreadID, LPVOID pParam)
{
	if (nThreadID == THREAD_SEND_RPN_TASK)
	{
		bool bRet = ReadPrnDataSendToMemMap();

		if (bRet)
			return 0;
		else
			return 1;
	}
	return 0;
}

int CDemoDlg::ThreadStop(int nThreadID)
{
	return 0;
}

void CDemoDlg::OnBnClickedBtnClose()
{
	
}

void CDemoDlg::OnBnClickedBtnStart()
{
	bool bOpened = IsOpendedMemMap();
	if (!bOpened)
	{
		int nRet = OpenAutoPrintPort_Rip();
		if (nRet != HPE_SUCEES)
		{
			MessageBox(_T("打开内存映射失败！"));
			return;
		}
	}

	m_dbProgress = 0;
	int nRet = CDlgThread::RunThread(this, THREAD_SEND_RPN_TASK, _T("正在发送PRN文件..."), FALSE, NULL);
	if (nRet != 0)
	{
		MessageBox(_T("发送失败"));
	}
	else
	{
		MessageBox(_T("发送完成"));
	}
}

CString CDemoDlg::GetCurFolder()
{
	TCHAR szExePath[MAX_PATH * 2 + 2] = { 0 };
	CString strCurPath;

	GetModuleFileName(NULL, szExePath, MAX_PATH * 2 + 2);
	strCurPath = szExePath;
	strCurPath = strCurPath.Mid(0, strCurPath.ReverseFind(_T('\\')) + 1);

	return strCurPath;
}

void CDemoDlg::OnBnClickedBtnOpenPrn()
{
	CFileDialog dlg(TRUE, NULL, NULL, NULL, _T("Rip Files (*.prn,*.prt)|*.prn;*.prt||"), NULL, 0, TRUE);

	dlg.m_ofn.lpstrTitle		= _T("选择文件");
	dlg.m_ofn.lpstrInitialDir	= m_szFilename;

	if (dlg.DoModal() == IDOK)
	{
		m_szFilename = dlg.GetPathName();

		theApp.WriteProfileString(_T("HsRipMemMap-Demo"), _T("FILE"), m_szFilename);

		UpdateData(FALSE);
	}
}

void CDemoDlg::OnBnClickedBtnStartMm()
{
	int nRet = OpenAutoPrintPort_Rip();
	if (nRet != HPE_SUCEES)
	{
		MessageBox(_T("打开内存映射失败！"));
	}
}

void CDemoDlg::OnBnClickedBtnCloseMm()
{
	int nRet = CloseAutoPrintPort_Rip();
	if (nRet != HPE_SUCEES)
	{
		MessageBox(_T("关闭内存映射失败！"));
	}
}