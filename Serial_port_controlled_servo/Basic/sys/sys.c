#include "sys.h"

void NVIC_Configuration(void){ //嵌套中断向量控制器 的设置
    NVIC_PriorityGroupConfig(NVIC_PriorityGroup_2);	//设置NVIC中断分组2:2位抢占优先级，2位响应优先级
}
void RCC_Configuration(void){ //RCC时钟的设置  
	ErrorStatus HSEStartUpStatus;   
	RCC_DeInit();              /* RCC system reset(for debug purpose) RCC寄存器恢复初始化值*/   
	RCC_HSEConfig(RCC_HSE_ON); /* Enable HSE 使能外部高速晶振*/   
	HSEStartUpStatus = RCC_WaitForHSEStartUp(); /* Wait till HSE is ready 等待外部高速晶振使能完成*/   
	if(HSEStartUpStatus == SUCCESS){   
		RCC_PLLConfig(RCC_PLLSource_HSE_Div1, RCC_PLLMul_9); //RCC_PLLMul_x（枚举2~16）是倍频值。当HSE=8MHZ,RCC_PLLMul_9时PLLCLK=72MHZ   
		/*设置AHB时钟（HCLK）*/   
		RCC_HCLKConfig(RCC_SYSCLK_Div1); //RCC_SYSCLK_Div1——AHB时钟 = 系统时钟(SYSCLK) = 72MHZ（外部晶振8HMZ）   
		RCC_PCLK1Config(RCC_HCLK_Div2); //设置低速AHB时钟（PCLK1）,RCC_HCLK_Div2——APB1时钟 = HCLK/2 = 36MHZ（外部晶振8HMZ）   
		RCC_PCLK2Config(RCC_HCLK_Div1); //设置高速AHB时钟（PCLK2）,RCC_HCLK_Div1——APB2时钟 = HCLK = 72MHZ（外部晶振8HMZ）   
		FLASH_SetLatency(FLASH_Latency_2); //设置FLASH存储器延时时钟周期数   
 
		FLASH_PrefetchBufferCmd(FLASH_PrefetchBuffer_Enable); //选择FLASH预取指缓存的模式，预取指缓存使能   
		RCC_PLLCmd(ENABLE);	//使能PLL
		while(RCC_GetFlagStatus(RCC_FLAG_PLLRDY) == RESET); //等待PLL输出稳定   
		RCC_SYSCLKConfig(RCC_SYSCLKSource_PLLCLK); //选择SYSCLK时钟源为PLL
		while(RCC_GetSYSCLKSource() != 0x08); //等待PLL成为SYSCLK时钟源   
	}  

	RCC_APB2PeriphClockCmd(RCC_APB2Periph_USART1 | RCC_APB2Periph_GPIOA | RCC_APB2Periph_GPIOB, ENABLE); //APB2外设时钟使能      

}  

