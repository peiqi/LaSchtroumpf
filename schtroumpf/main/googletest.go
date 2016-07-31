package main

import (
	"fmt"
	"os"
	"strconv"
)

func recusive(N int) int {

	var i int = N
	var Sum int = 0

	switch {

	case i == 1:
		Sum += 1
	case i == 2:
		Sum += 2
	case i == 3:
		Sum += 4
	case i > 3:
		Sum = recusive(i-1) + recusive(i-2) + recusive(i-3)
	}

	return Sum
}

func count(Seq []int, N int) {

	var i int = N

	if i >= 1 {
		Seq = append(Seq, 1)
		count(Seq, i-1)
	}

	if i >= 2 {
		Seq = append(Seq, 2)
		count(Seq, i-2)
	}

	if i >= 3 {
		Seq = append(Seq, 3)
		count(Seq, i-3)
	}

	if i == 0 {

		//for _,q := range Seq {
			fmt.Printf("the summation is %d \n", Seq)
			//fmt.Printf("the summation is %d \n", Seq)
		//}
	}
}

func main() {

	if len(os.Args) != 2 {
		fmt.Printf("Usage %s is required for a number to count", os.Args[1])
	}
	kk, _ := strconv.Atoi(os.Args[1])
	qq := make([]int, 0)
	n := recusive(kk)
	count(qq, kk)
	//fmt.Printf("the Sum is %d and %s \n", kk)
	fmt.Printf("the Sum is %d \n", n)
}
